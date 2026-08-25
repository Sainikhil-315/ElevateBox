import asyncio
import base64
import json
from typing import AsyncIterator
import base64

from src.config import get_settings

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


def _listen_url() -> str:
    s = get_settings()
    params = (
        "encoding=mulaw&sample_rate=8000"
        f"&model=nova-3&language={s.deepgram_language}"
        "&punctuate=true&endpointing=200&utterance_end_ms=1000&interim_results=true"
    )
    return f"{DEEPGRAM_WS_URL}?{params}"


class DeepgramStream:
    def __init__(self, api_key: str | None = None):
        s = get_settings()
        self.api_key = api_key or s.deepgram_api_key
        self.ws = None
        self._receiver = None
        self._closed = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start(self) -> None:
        import websockets

        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not configured")
        try:
            self.ws = await websockets.connect(
                _listen_url(),
                additional_headers={"Authorization": f"Token {self.api_key}"},
                max_size=None,
            )
        except websockets.exceptions.InvalidStatus as e:
            body = e.response.body.decode(errors="replace") if e.response.body else "(empty)"
            headers_list = list(e.response.headers.raw_items())
            print(f"DEEPGRAM REJECTED: status={e.response.status_code} body={body!r} headers={headers_list}")
            raise
        self._receiver = asyncio.create_task(self._receive_loop())
    async def _receive_loop(self) -> None:
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type == "Results":
                    alt = (data.get("channel", {}).get("alternatives") or [{}])[0]
                    transcript = alt.get("transcript", "").strip()
                    if transcript:
                        await self._queue.put(
                            {
                                "text": transcript,
                                "confidence": alt.get("confidence", 0.0),
                                "is_final": data.get("is_final", False),
                                "speech_final": data.get("speech_final", False),
                            }
                        )
                elif msg_type == "UtteranceEnd":
                    await self._queue.put({"text": "", "confidence": 0.0, "is_final": False, "utterance_end": True})
                elif msg_type in ("CloseStream", "Error"):
                    break
        except Exception:
            pass
        finally:
            self._closed = True
            await self._queue.put(None)

    async def send_audio(self, mulaw_b64: str) -> None:
        if self.ws and not self._closed:
            raw = base64.b64decode(mulaw_b64)
            await self.ws.send(raw)

    async def transcripts(self) -> AsyncIterator[dict]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def finish(self) -> None:
        self._closed = True
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        if self._receiver:
            self._receiver.cancel()
