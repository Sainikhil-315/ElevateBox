import asyncio
import logging
import re

from src.db import append_turn, get_call, update_call_fields
from src.llm.turn_manager import TurnManager
from src.llm import client as llm_client
from src.stt.deepgram_stt import DeepgramStream
from src.tts.google_tts import TTSError, synthesize_mulaw
import base64

logger = logging.getLogger("voice-agent.media")

# Sentence boundary: split on punctuation followed by whitespace
SENTENCE_END = re.compile(r"[.?!।…]+(?:\s|$)")
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
        self._dg_preconnect_task: asyncio.Task | None = None

    async def _send(self, message: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        # ── FIX 1: Pre-connect Deepgram immediately so it's ready when call starts ──
        self.dg = DeepgramStream()
        self._dg_preconnect_task = asyncio.create_task(self._preconnect_deepgram())

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
                    # Wait for pre-connect to finish (usually already done by now)
                    if self._dg_preconnect_task:
                        try:
                            await self._dg_preconnect_task
                        except Exception:
                            logger.warning("Pre-connect failed, retrying Deepgram start call=%s", self.call_sid)
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

    async def _preconnect_deepgram(self) -> None:
        """Connect Deepgram WebSocket immediately so it's ready by the time audio arrives."""
        try:
            await self.dg.start()
            logger.info("Deepgram pre-connected successfully")
        except Exception:
            logger.exception("Deepgram pre-connect failed")

    async def _noop(self) -> None:
        await asyncio.sleep(3600)

    async def _open_call(self) -> None:
        import time as _time

        await asyncio.sleep(0.6)
        if self._stopped:
            return
        self.last_user_activity = _time.monotonic()
        logger.info("GREETING call=%s: proactive opening", self.call_sid)
        # Greeting is in Hindi/Hinglish — set language state to match
        self.turn_manager.state.language = "hi"
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

        # Detect explicit language-switch commands and override immediately
        _tl = text.lower()
        if any(w in _tl for w in ("speak english", "in english", "english mein", "english me", "english please", "talk english")):
            self.turn_manager.state.language = "en"
            logger.info("LANG-OVERRIDE call=%s: forced to English", self.call_sid)
        elif any(w in _tl for w in ("hindi mein", "hindi me", "speak hindi", "in hindi", "hindi boliye")):
            self.turn_manager.state.language = "hi"
            logger.info("LANG-OVERRIDE call=%s: forced to Hindi", self.call_sid)
        elif any(w in _tl for w in ("telugu", "telugu lo", "telugu mein")):
            self.turn_manager.state.language = "te"
            logger.info("LANG-OVERRIDE call=%s: forced to Telugu", self.call_sid)

        # Add user utterance to in-memory history so the LLM sees it
        self.turn_manager.state.history.append({"role": "user", "content": text})

        # ── Streaming pipeline — speak each sentence as soon as LLM emits it ──
        self._speak_task = asyncio.current_task()
        await self._stream_reply(text)

    async def _stream_reply(self, user_text: str) -> None:
        """Stream LLM tokens → sentence splitter → TTS → audio, sentence by sentence.
        Also collects the full reply for logging and DB persistence."""
        import time as _time
        from src.llm.turn_manager import _parse_action_block, _normalize, FALLBACK_REPLIES

        t0 = _time.perf_counter()
        messages = self.turn_manager.build_messages(self.turn_manager.state.context_note())

        full_reply_parts: list[str] = []
        sentence_buf = ""
        language = self.turn_manager.state.language
        first_sentence_spoken = False
        used_fallback = False

        self.bot_speaking = True
        self.last_bot_text = ""

        async def _tts_and_play(sentence: str) -> None:
            """Synthesize one sentence and send its audio frames."""
            nonlocal first_sentence_spoken
            if not sentence.strip() or not self.bot_speaking or self._stopped:
                return
            try:
                audio = await asyncio.get_running_loop().run_in_executor(
                    None, synthesize_mulaw, sentence.strip(), language
                )
            except TTSError:
                logger.exception("TTS failed call=%s", self.call_sid)
                return
            if not self.bot_speaking or self._stopped:
                return
            if not first_sentence_spoken:
                logger.info("FIRST-AUDIO call=%s latency=%.0fms", self.call_sid,
                            (_time.perf_counter() - t0) * 1000)
                first_sentence_spoken = True
            await self._send_audio_frames(audio)

        try:
            settings = __import__("src.config", fromlist=["get_settings"]).get_settings()
            stream = llm_client.chat_with_first_token_timeout(
                messages, timeout_s=settings.llm_timeout_first_token
            )
            async for token in stream:
                if not self.bot_speaking or self._stopped:
                    break
                sentence_buf += token
                full_reply_parts.append(token)
                self.last_bot_text += token

                # Check for sentence boundary
                while True:
                    m = SENTENCE_END.search(sentence_buf)
                    if not m:
                        break
                    end = m.end()
                    sentence = sentence_buf[:end]
                    sentence_buf = sentence_buf[end:]
                    # Don't speak action marker lines
                    if "@@@" not in sentence:
                        await _tts_and_play(sentence)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("LLM stream error call=%s", self.call_sid)
            used_fallback = True

        # Speak any remaining buffer (sentence without trailing punctuation)
        remainder = sentence_buf.strip()
        if remainder and "@@@" not in remainder and self.bot_speaking and not self._stopped:
            await _tts_and_play(remainder)

        # If nothing was spoken at all, use fallback
        if not first_sentence_spoken and not self._stopped:
            fallback_text = FALLBACK_REPLIES.get(language, FALLBACK_REPLIES["en"])
            await self.speak(fallback_text, language)
            full_reply_parts = [fallback_text]
            used_fallback = True
            # Remove the dangling user turn so the LLM doesn't see an unanswered
            # message — the user will retry and we'll try the LLM again cleanly
            if self.turn_manager.state.history and self.turn_manager.state.history[-1]["role"] == "user":
                self.turn_manager.state.history.pop()

        latency_ms = int((_time.perf_counter() - t0) * 1000)
        raw = "".join(full_reply_parts)
        spoken, data = _parse_action_block(raw)
        parsed = _normalize(data) if data else {}

        # Update turn manager state and history
        classification = self.turn_manager.state.apply(parsed) if parsed else self.turn_manager.state.classification
        action = parsed.get("action") if parsed else None
        reply_text = spoken or (FALLBACK_REPLIES.get(language, FALLBACK_REPLIES["en"]))
        self.last_bot_text = reply_text
        # Only add to history if it's a real LLM reply (not a fallback), so
        # the next turn doesn't see "Sorry, could you say that again" as context
        if not used_fallback:
            self.turn_manager.state.history.append({"role": "assistant", "content": reply_text})
        if parsed.get("language") in ("te", "hi", "en"):
            language = parsed["language"]

        # Persist turn & update call fields
        append_turn(self.call_sid, "assistant", reply_text, latency_ms=latency_ms)
        update_call_fields(
            self.call_sid,
            language=language,
            classification=classification,
            barrier=self.turn_manager.state.barrier,
        )

        prev_cls = getattr(self, "last_classification", None)
        if prev_cls and prev_cls != classification:
            logger.info(
                "LEAD-CHANGE call=%s: %s -> %s",
                self.call_sid, prev_cls.upper(), classification.upper(),
            )
        self.last_classification = classification

        signals = parsed.get("signals", [])
        sig_parts = [
            f'{s.get("type", "?")}/{s.get("polarity", "?")} ["{(s.get("quote") or "")[:50]}"]'
            for s in signals
        ]
        logger.info(
            "INTENT call=%s lang=%s lead=%s barrier=%s action=%s signals=[%s]",
            self.call_sid, language, classification.upper(),
            self.turn_manager.state.barrier or "none", action,
            " | ".join(sig_parts) if sig_parts else "none detected",
        )
        logger.info(
            "BOT call=%s latency=%dms fallback=%s says: %s",
            self.call_sid, latency_ms, used_fallback, reply_text[:80],
        )

        # Run any mid-call actions (WhatsApp dispatch etc.)
        if action:
            from src.whatsapp.dispatcher import dispatch_mid_call_actions
            from dataclasses import dataclass
            # Build a minimal result-like object for the dispatcher
            class _R:
                pass
            r = _R()
            r.reply = reply_text; r.classification = classification
            r.confidence = parsed.get("confidence", 0)
            r.barrier = self.turn_manager.state.barrier
            r.language = language; r.signals = signals; r.action = action
            r.latency_ms = latency_ms; r.used_fallback = used_fallback
            await dispatch_mid_call_actions(self.call_sid, r, get_call(self.call_sid) or {})

        if self._speak_task is asyncio.current_task():
            self._speak_task = None
            self.bot_speaking = False

    async def _run_actions(self, result) -> None:
        from src.whatsapp.dispatcher import dispatch_mid_call_actions

        await dispatch_mid_call_actions(self.call_sid, result, get_call(self.call_sid) or {})

    async def speak(self, text: str, language: str = "en") -> None:
        self.last_bot_text = text
        self._speak_task = asyncio.current_task()
        self.bot_speaking = True
        try:
            sentences = [s for s in SENTENCE_END.split(text.strip()) if s.strip()]
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
