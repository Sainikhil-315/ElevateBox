import asyncio
import json
from typing import AsyncIterator

import httpx

from src.config import get_settings


class LLMError(Exception):
    pass


def _api_key() -> str:
    s = get_settings()
    return s.gemini_api_key or s.openrouter_api_key


async def stream_chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 300) -> AsyncIterator[str]:
    s = get_settings()
    key = _api_key()
    if not key:
        raise LLMError("No LLM API key configured")

    body = {"model": s.openrouter_model, "messages": messages, "stream": True, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Authorization": f"Bearer {key}"}
    if "openrouter" in s.llm_base_url:
        headers["HTTP-Referer"] = "https://github.com/Sainikhil-315/ElevateBox"
        headers["X-Title"] = "ElevateBox Voice Agent"

    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{s.llm_base_url.rstrip('/')}/chat/completions", json=body, headers=headers) as r:
            if r.status_code != 200:
                detail = (await r.aread()).decode(errors="replace")[:300]
                raise LLMError(f"LLM HTTP {r.status_code}: {detail}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    return
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = (data.get("choices") or [{}])[0]
                piece = choice.get("delta", {}).get("content") or ""
                if piece:
                    yield piece


async def chat_with_first_token_timeout(messages: list[dict], timeout_s: float | None = None) -> AsyncIterator[str]:
    s = get_settings()
    limit = timeout_s if timeout_s is not None else s.llm_timeout_first_token
    gen = stream_chat(messages)
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        raise LLMError("LLM returned empty stream")
    except httpx.TimeoutException:
        raise LLMError("LLM connection timeout")
    yield first
    async for piece in gen:
        yield piece


async def chat_once(messages: list[dict], temperature: float = 0.0, max_tokens: int = 300) -> str:
    chunks = []
    async for piece in stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
        chunks.append(piece)
    return "".join(chunks)


async def timed_chat_once(messages: list[dict], timeout_s: float) -> str:
    return await asyncio.wait_for(chat_once(messages), timeout=timeout_s)
