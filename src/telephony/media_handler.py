import asyncio
import logging
import re

from src.db import append_turn, get_call, update_call_fields
from src.llm.turn_manager import TurnManager
from src.stt.deepgram_stt import DeepgramStream
from src.tts.google_tts import TTSError, synthesize_mulaw
import base64

logger = logging.getLogger("voice-agent.media")

SENTENCE_SPLIT = re.compile(r"(?<=[.?!।])\s+")
FRAME_BYTES = 1600

MIN_UTTERANCE_CHARS = 2
MIN_CONFIDENCE = 0.5

GREETING = (
    "Hello! Main Priya bol rahi hoon Nikhil Studios se. "
    "Aapke business ko online badhane ke liye e-commerce website ke baare mein baat karni thi. "
    "Ek minute mil sakte hain?"
)

NUDGES = [
    "Hello? Sun rahe hain aap?",
    "Main sun rahi hoon, jab aap ready ho bataiye.",
]
SILENCE_NUDGE_AFTER = 8.0
SILENCE_NUDGE_REPEAT = 12.0
MAX_NUDGES = 2


def _overlap_ratio(a: str, b: str) -> float:
    aw = set(a.lower().split())
    bw = set(b.lower().split())
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / min(len(aw), len(bw))


class MediaSession:
    def __init__(self, ws):
        self.ws = ws
        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.turn_manager: TurnManager | None = None
        self.dg: DeepgramStream | None = None
        self._send_lock = asyncio.Lock()
        self._speak_task: asyncio.Task | None = None
        self.bot_speaking = False
        self.last_bot_text = ""
        self._utterance_buffer: list[str] = []
        self._stopped = False
        self.last_user_activity = 0.0
        self._nudges_sent = 0
        self._watchdog: asyncio.Task | None = None

    async def _send(self, message: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        consumer = asyncio.create_task(self._noop())
        try:
            while True:
                msg = await self.ws.receive_json()
                event = msg.get("event")
                if event == "start":
                    start = msg.get("start", {})
                    self.stream_sid = start.get("streamSid")
                    params = start.get("customParameters", {})
                    self.call_sid = params.get("call_sid") or start.get("callSid")
                    self.turn_manager = TurnManager(self.call_sid or "unknown")
                    self.dg = DeepgramStream()
                    await self.dg.start()
                    consumer.cancel()
                    consumer = asyncio.create_task(self._transcript_consumer())
                    asyncio.create_task(self._open_call())
                    logger.info("Media session started: call=%s stream=%s", self.call_sid, self.stream_sid)
                elif event == "media":
                    if self.dg:
                        await self.dg.send_audio(msg.get("media", {}).get("payload", ""))
                elif event == "stop":
                    break
        except Exception:
            logger.exception("Media session error call=%s", self.call_sid)
        finally:
            self._stopped = True
            consumer.cancel()
            if self._watchdog:
                self._watchdog.cancel()
            if self._speak_task:
                self._speak_task.cancel()
            if self.dg:
                await self.dg.finish()

    async def _noop(self) -> None:
        await asyncio.sleep(3600)

    async def _open_call(self) -> None:
        import time as _time

        await asyncio.sleep(0.6)
        if self._stopped:
            return
        self.last_user_activity = _time.monotonic()
        logger.info("GREETING call=%s: proactive opening", self.call_sid)
        await self.speak(GREETING, "hi")
        if self._stopped:
            return
        self._watchdog = asyncio.create_task(self._silence_watchdog())

    async def _silence_watchdog(self) -> None:
        import time as _time

        try:
            while not self._stopped and self._nudges_sent < MAX_NUDGES:
                await asyncio.sleep(1.0)
                if self.bot_speaking or not self.stream_sid:
                    continue
                quiet_for = _time.monotonic() - self.last_user_activity
                threshold = SILENCE_NUDGE_AFTER if self._nudges_sent == 0 else SILENCE_NUDGE_REPEAT
                if quiet_for >= threshold:
                    nudge = NUDGES[self._nudges_sent]
                    self._nudges_sent += 1
                    logger.info("SILENCE call=%s: nudge %d after %.0fs quiet", self.call_sid, self._nudges_sent, quiet_for)
                    await self.speak(nudge, "hi")
        except asyncio.CancelledError:
            pass

    async def _transcript_consumer(self) -> None:
        try:
            async for item in self.dg.transcripts():
                if self._stopped:
                    return
                text = item.get("text", "")
                confidence = item.get("confidence", 0.0)
                if item.get("utterance_end"):
                    await self._flush_utterance()
                    continue
                if not item.get("is_final"):
                    if self.bot_speaking and len(text) >= MIN_UTTERANCE_CHARS:
                        await self._maybe_barge_in(text)
                    continue
                if text and len(text) >= MIN_UTTERANCE_CHARS and confidence >= MIN_CONFIDENCE:
                    self._utterance_buffer.append(text)
                    if item.get("speech_final"):
                        await self._flush_utterance()
                    elif self.bot_speaking:
                        await self._maybe_barge_in(text)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Transcript consumer error")

    async def _maybe_barge_in(self, heard: str) -> None:
        if not self.bot_speaking:
            return
        if _overlap_ratio(heard, self.last_bot_text) > 0.7:
            return
        await self.interrupt()

    async def interrupt(self) -> None:
        if not self.bot_speaking:
            return
        self.bot_speaking = False
        if self._speak_task:
            self._speak_task.cancel()
            self._speak_task = None
        if self.stream_sid:
            await self._send({"event": "clear", "streamSid": self.stream_sid})
        logger.info("Barge-in: cleared audio call=%s", self.call_sid)

    async def _flush_utterance(self) -> None:
        if not self._utterance_buffer:
            return
        text = " ".join(self._utterance_buffer).strip()
        self._utterance_buffer.clear()
        if not text:
            return
        await self._handle_user_utterance(text)

    async def _handle_user_utterance(self, text: str) -> None:
        if _overlap_ratio(text, self.last_bot_text) > 0.8:
            logger.info("Echo suppressed call=%s", self.call_sid)
            return
        if self.bot_speaking:
            await self.interrupt()

        import time as _time

        self.last_user_activity = _time.monotonic()
        self._nudges_sent = 0
        append_turn(self.call_sid, "user", text)
        logger.info("USER call=%s says: %s", self.call_sid, text)
        result = await self.turn_manager.handle_transcript(text)
        append_turn(
            self.call_sid,
            "assistant",
            result.reply,
            latency_ms=result.latency_ms,
        )
        update_call_fields(
            self.call_sid,
            language=result.language,
            classification=result.classification,
            barrier=result.barrier,
        )

        prev_cls = getattr(self, "last_classification", None)
        if prev_cls and prev_cls != result.classification:
            logger.info(
                "LEAD-CHANGE call=%s: %s -> %s",
                self.call_sid, prev_cls.upper(), result.classification.upper(),
            )
        self.last_classification = result.classification

        sig_parts = []
        for s in result.signals:
            sig_parts.append(
                f'{s.get("type", "?")}/{s.get("polarity", "?")} ["{(s.get("quote") or "")[:50]}"]'
            )
        logger.info(
            "INTENT call=%s lang=%s lead=%s(conf=%d) barrier=%s action=%s signals=[%s]",
            self.call_sid,
            result.language,
            result.classification.upper(),
            result.confidence,
            result.barrier or "none",
            result.action,
            " | ".join(sig_parts) if sig_parts else "none detected",
        )
        logger.info(
            "BOT call=%s latency=%dms fallback=%s says: %s",
            self.call_sid, result.latency_ms, result.used_fallback, result.reply[:80],
        )
        await self._run_actions(result)
        await self.speak(result.reply, result.language)

    async def _run_actions(self, result) -> None:
        from src.whatsapp.dispatcher import dispatch_mid_call_actions

        await dispatch_mid_call_actions(self.call_sid, result, get_call(self.call_sid) or {})

    async def speak(self, text: str, language: str = "en") -> None:
        self.last_bot_text = text
        self._speak_task = asyncio.current_task()
        self.bot_speaking = True
        try:
            sentences = [s for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]
            if not sentences:
                sentences = [text.strip()]
            for sentence in sentences:
                if not self.bot_speaking or self._stopped:
                    return
                try:
                    audio = await asyncio.get_running_loop().run_in_executor(
                        None, synthesize_mulaw, sentence, language
                    )
                except TTSError:
                    logger.exception("TTS failed call=%s", self.call_sid)
                    return
                if not self.bot_speaking or self._stopped:
                    return
                await self._send_audio_frames(audio)
        except asyncio.CancelledError:
            raise
        finally:
            if self._speak_task is asyncio.current_task():
                self._speak_task = None
                self.bot_speaking = False

    async def _send_audio_frames(self, audio: bytes) -> None:
        for offset in range(0, len(audio), FRAME_BYTES):
            if not self.bot_speaking or self._stopped:
                return
            chunk = audio[offset:offset + FRAME_BYTES]
            await self._send(
                {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": base64.b64encode(chunk).decode()},
                }
            )
