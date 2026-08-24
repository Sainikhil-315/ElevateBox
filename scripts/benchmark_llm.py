import asyncio
import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]

SENTENCE_END = re.compile(r"[.?!।]\s|$")

LATENCY_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are Priya, a friendly sales agent calling a shop owner about building "
            "an e-commerce website for their business. Reply in the same language and "
            "style the customer uses, including code-switching. Keep replies under 40 "
            "words, natural spoken style."
        ),
    },
    {
        "role": "user",
        "content": "Naa duukaan mein clothes vuntayi. Website kavali but budget takkuva, entha avtundi?",
    },
]

CLASSIFICATION_SYSTEM = (
    "You classify a caller's buying intent from one turn of a sales call about "
    "e-commerce website development. Respond with ONLY valid JSON, no markdown, no "
    "extra text, matching exactly:\n"
    '{"signals": [{"quote": string, "type": string, "polarity": string}], '
    '"classification": "hot"|"warm"|"cold", "confidence": number, '
    '"barrier": null|"budget"|"timing"|"decision_maker"|"other"}'
)

CLASSIFICATION_TURNS = [
    "Send me the details on WhatsApp, how soon can you start?",
    "My brother handles all this, talk to him only.",
    "Budget is not much right now, maybe next year.",
    "Haan website kavali, monthly 500 orders vasthayi online lo, ee month lo start cheyali.",
    "Just looking, not interested now.",
]

REQUIRED_KEYS = {"signals", "classification", "confidence", "barrier"}
VALID_CLASSES = {"hot", "warm", "cold"}

EXPECTED = ["hot", "warm", "warm", "hot", "cold"]


def strip_fences(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def run_latency(client, api_key, model):
    body = {"model": model, "messages": LATENCY_MESSAGES, "stream": True}
    headers = {"Authorization": f"Bearer {api_key}"}
    t0 = time.perf_counter()
    ttft = None
    first_sentence_time = None
    buffer = ""
    out_chars = 0
    async with client.stream("POST", API_URL, json=body, headers=headers) as r:
        if r.status_code != 200:
            detail = (await r.aread()).decode(errors="replace")[:200]
            return {"error": f"HTTP {r.status_code}: {detail}"}
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta", {})
            piece = delta.get("content") or ""
            if not piece:
                continue
            if ttft is None:
                ttft = time.perf_counter() - t0
            buffer += piece
            out_chars += len(piece)
            if first_sentence_time is None and SENTENCE_END.search(buffer.strip()):
                first_sentence_time = time.perf_counter() - t0
    total = time.perf_counter() - t0
    return {
        "ttft_s": round(ttft, 3) if ttft else None,
        "first_sentence_s": round(first_sentence_time, 3) if first_sentence_time else None,
        "total_s": round(total, 3),
        "output_chars": out_chars,
        "chars_per_s": round(out_chars / total, 1) if total > 0 else None,
        "preview": buffer[:120],
    }


async def run_json(client, api_key, model, turn):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": CLASSIFICATION_SYSTEM},
            {"role": "user", "content": turn},
        ],
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    t0 = time.perf_counter()
    r = await client.post(API_URL, json=body, headers=headers)
    elapsed = round(time.perf_counter() - t0, 3)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}", "elapsed_s": elapsed}
    content = r.json()["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(strip_fences(content))
        valid_keys = REQUIRED_KEYS.issubset(parsed.keys())
        valid_class = parsed.get("classification") in VALID_CLASSES
        return {
            "elapsed_s": elapsed,
            "json_valid": bool(valid_keys and valid_class),
            "classification": parsed.get("classification"),
        }
    except (json.JSONDecodeError, TypeError):
        return {"elapsed_s": elapsed, "json_valid": False, "classification": None}


def summarize(rows, key):
    vals = [r[key] for r in rows if isinstance(r, dict) and r.get(key) is not None]
    if not vals:
        return None
    return {
        "median": round(statistics.median(vals), 3),
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
    }


async def benchmark(api_key, models, runs):
    async with httpx.AsyncClient(timeout=60) as client:
        for model in models:
            print(f"\n=== {model} ===")
            lat_rows = []
            for i in range(runs):
                row = await run_latency(client, api_key, model)
                lat_rows.append(row)
                status = row.get("error") or f"ttft={row.get('ttft_s')}s first_sentence={row.get('first_sentence_s')}s"
                print(f"  latency run {i+1}/{runs}: {status}")
            print(f"  TTFT median:          {summarize(lat_rows, 'ttft_s')}")
            print(f"  First-sentence med:   {summarize(lat_rows, 'first_sentence_s')}")
            print(f"  Total median:         {summarize(lat_rows, 'total_s')}")

            json_rows = []
            for turn, expected in zip(CLASSIFICATION_TURNS, EXPECTED):
                row = await run_json(client, api_key, model, turn)
                row["expected"] = expected
                json_rows.append(row)
                mark = "OK " if row.get("classification") == expected else "BAD"
                err = row.get("error", "")
                print(f"  json [{mark}] expected={expected} got={row.get('classification')} ({row.get('elapsed_s','?')}s) {err}")

            valid = sum(1 for r in json_rows if r.get("json_valid"))
            correct = sum(1 for r in json_rows if r.get("classification") == r["expected"])
            print(f"  JSON validity: {valid}/{len(json_rows)} | classification accuracy: {correct}/{len(json_rows)}")


def main():
    parser = argparse.ArgumentParser(description="OpenRouter free-model latency & quality benchmark")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("ERROR: set OPENROUTER_API_KEY in environment or .env")
        sys.exit(1)

    asyncio.run(benchmark(api_key, args.models, args.runs))


if __name__ == "__main__":
    main()
