import asyncio
import json
from typing import AsyncIterator

import httpx

from src.config import get_settings


class LLMError(Exception):
    pass


def _resolve_provider() -> tuple[str, str, str]:
    """Returns (api_key, model, base_url) for the currently active provider,
    based on LLM_PROVIDER in settings ('groq' | 'gemini' | 'openai')."""
    s = get_settings()
    provider = (s.llm_provider or "groq").lower()
    if provider == "groq":
        return s.groq_api_key, s.groq_model, s.groq_base_url
    if provider == "gemini":
        return s.gemini_api_key, s.gemini_model, s.gemini_base_url
    if provider == "openai":
        return s.openai_api_key, s.openai_model, s.openai_base_url
    raise LLMError(f"Unknown LLM_PROVIDER: {provider!r} (expected groq | gemini | openai)")


async def stream_chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1500) -> AsyncIterator[str]:
    s = get_settings()
    key, model, base_url = _resolve_provider()
    if not key:
        raise LLMError(f"No API key configured for provider '{s.llm_provider}'")

    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # reasoning_effort is an OpenRouter/Gemini-specific param; only send it for that provider
    if s.llm_reasoning_effort and s.llm_provider.lower() == "gemini":
        body["reasoning_effort"] = s.llm_reasoning_effort

    headers = {"Authorization": f"Bearer {key}"}
    if "openrouter" in base_url:
        headers["HTTP-Referer"] = "https://github.com/Sainikhil-315/ElevateBox"
        headers["X-Title"] = "ElevateBox Voice Agent"

    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", f"{base_url.rstrip('/')}/chat/completions", json=body, headers=headers
        ) as r:
            if r.status_code != 200:
                detail = (await r.aread()).decode(errors="replace")[:300]
                raise LLMError(f"LLM HTTP {r.status_code} [{s.llm_provider}/{model}]: {detail}")
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
        first = await asyncio.wait_for(gen.__anext__(), timeout=limit)
    except StopAsyncIteration:
        raise LLMError("LLM returned empty stream")
    except asyncio.TimeoutError:
        raise LLMError("LLM first-token timeout")
    except httpx.TimeoutException:
        raise LLMError("LLM connection timeout")
    yield first
    async for piece in gen:
        yield piece


async def chat_once(messages: list[dict], temperature: float = 0.0, max_tokens: int = 1500) -> str:
    chunks = []
    async for piece in stream_chat(messages, temperature=temperature, max_tokens=max_tokens):
        chunks.append(piece)
    return "".join(chunks)


async def timed_chat_once(messages: list[dict], timeout_s: float) -> str:
    return await asyncio.wait_for(chat_once(messages), timeout=timeout_s)