import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.llm import client as llm_client
from src.config import get_settings

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

ACTION_MARKER = "@@@"

VALID_CLASSES = {"hot", "warm", "cold"}
VALID_BARRIERS = {None, "budget", "timing", "decision_maker", "other"}
VALID_LANGS = {"te", "hi", "en"}


@dataclass
class TurnResult:
    reply: str
    classification: str = "cold"
    confidence: int = 0
    barrier: str | None = None
    language: str = "en"
    signals: list[dict] = field(default_factory=list)
    action: dict | None = None
    latency_ms: int = 0
    used_fallback: bool = False


def load_system_prompt() -> str:
    return (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8")


def _parse_action_block(text: str) -> tuple[str, dict | None]:
    if ACTION_MARKER not in text:
        return text.strip(), None
    spoken, _, blob = text.partition(ACTION_MARKER)
    blob = blob.strip()
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", blob, re.DOTALL)
        if not m:
            return spoken.strip(), None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return spoken.strip(), None
    return spoken.strip(), data


def _normalize(data: dict) -> dict:
    cls = str(data.get("classification", "")).lower()
    barrier = data.get("barrier")
    if barrier in ("", "none"):
        barrier = None
    lang = str(data.get("language", "en")).lower()
    return {
        "classification": cls if cls in VALID_CLASSES else None,
        "confidence": int(data.get("confidence") or 0),
        "barrier": barrier if barrier in VALID_BARRIERS else None,
        "language": lang if lang in VALID_LANGS else "en",
        "signals": data.get("signals") if isinstance(data.get("signals"), list) else [],
        "action": data.get("action") if isinstance(data.get("action"), dict) else None,
    }


class RunningState:
    def __init__(self):
        self.classification = "cold"
        self.confidence = 0
        self.barrier: str | None = None
        self.language = "en"
        self.rejections = 0
        self.positive_signals = 0
        self.history: list[dict] = []

    def apply(self, parsed: dict) -> str:
        cls = parsed["classification"]
        barrier = parsed["barrier"]
        signals = parsed["signals"] or []

        for sig in signals:
            t = str(sig.get("type", "")).lower()
            p = str(sig.get("polarity", "")).lower()
            quote = str(sig.get("quote", "")).lower()
            negative_words = ["not interested", "no need", "vaddu", "nahi chahiye", "oddu", "don't want"]
            if t == "deflection" or (p == "negative" and any(w in quote for w in negative_words)):
                self.rejections += 1
            elif p == "positive":
                self.positive_signals += 1

        barrier_accepted = False
        if barrier in ("budget", "timing", "decision_maker"):
            matching_negative = any(
                str(s.get("type", "")).lower() == barrier and str(s.get("polarity", "")).lower() == "negative"
                for s in signals
            )
            if matching_negative or parsed["confidence"] >= 75:
                self.barrier = barrier
                barrier_accepted = True
        elif barrier is None and parsed["confidence"] >= 60:
            self.barrier = None
            barrier_accepted = True

        proposed = cls if cls else self.classification
        has_timeline_question = any(
            str(s.get("type", "")).lower() == "timeline" and str(s.get("polarity", "")).lower() == "positive"
            for s in signals
        )
        has_budget_positive = any(
            str(s.get("type", "")).lower() == "budget" and str(s.get("polarity", "")).lower() == "positive"
            for s in signals
        )

        if has_timeline_question:
            proposed = max_cls(proposed, "warm")
        if has_budget_positive and has_timeline_question:
            proposed = max_cls(proposed, "hot")
        if self.barrier in ("budget", "timing", "decision_maker"):
            proposed = min_cls(proposed, "warm")
        if cls == "hot" and parsed["confidence"] >= 60 and not self.barrier:
            proposed = "hot"
        if self.rejections >= 2:
            proposed = "cold"

        order = ["cold", "warm", "hot"]
        if proposed in order and order.index(proposed) > order.index(self.classification):
            self.classification = proposed
        elif self.rejections >= 2:
            self.classification = "cold"

        self.confidence = parsed["confidence"]
        if parsed["language"] in VALID_LANGS:
            self.language = parsed["language"]
        return self.classification

    def context_note(self) -> str:
        lang_name = {"en": "English", "hi": "Hindi", "te": "Telugu"}.get(self.language, "English")
        parts = [
            f"Current lead status: {self.classification.upper()}",
            f"Current conversation language: {lang_name} — reply in {lang_name} unless the caller explicitly switches",
        ]
        if self.barrier:
            parts.append(f"Known barrier: {self.barrier}")
        if self.rejections:
            parts.append(f"Rejections so far: {self.rejections}")
        return "; ".join(parts)


def _max(a, b):
    order = ["cold", "warm", "hot"]
    return a if order.index(a) >= order.index(b) else b


def max_cls(a, b):
    return _max(a, b)


def min_cls(a, b):
    order = ["cold", "warm", "hot"]
    return a if order.index(a) <= order.index(b) else b


FALLBACK_REPLIES = {
    "en": "Sorry, could you say that again for me?",
    "hi": "Sorry, zara dobara boliye?",
    "te": "Kshaminchandi, malli cheppandi?",
}

FILLERS = {
    "en": "One second...",
    "hi": "Ek second...",
    "te": "Nimisham...",
}


class TurnManager:
    def __init__(self, call_sid: str):
        self.call_sid = call_sid
        self.state = RunningState()
        self._system_prompt = load_system_prompt()

    def build_messages(self, note: str | None = None) -> list[dict]:
        msgs = [{"role": "system", "content": self._system_prompt}]
        if note:
            msgs.append({"role": "system", "content": note})
        msgs.extend(self.state.history[-12:])
        return msgs

    async def handle_transcript(self, text: str, note: str | None = None) -> TurnResult:
        import time as _time

        self.state.history.append({"role": "user", "content": text})
        messages = self.build_messages(note)
        t0 = _time.perf_counter()

        raw = None
        used_fallback = False
        try:
            raw = await llm_client.timed_chat_once(messages, timeout_s=get_settings().llm_timeout_first_token * 4)
        except Exception:
            used_fallback = True

        if raw is None:
            try:
                raw = await llm_client.timed_chat_once(messages, timeout_s=8.0)
            except Exception:
                raw = None

        if not raw:
            reply = FALLBACK_REPLIES.get(self.state.language, FALLBACK_REPLIES["en"])
            return TurnResult(
                reply=reply,
                classification=self.state.classification,
                barrier=self.state.barrier,
                language=self.state.language,
                latency_ms=int((_time.perf_counter() - t0) * 1000),
                used_fallback=True,
            )

        spoken, data = _parse_action_block(raw)
        parsed = _normalize(data) if data else {}
        classification = self.state.apply(parsed) if parsed else self.state.classification
        action = parsed.get("action") if parsed else None

        if not spoken:
            spoken = FALLBACK_REPLIES.get(self.state.language, FALLBACK_REPLIES["en"])
            used_fallback = True

        self.state.history.append({"role": "assistant", "content": spoken})
        return TurnResult(
            reply=spoken,
            classification=classification,
            confidence=parsed.get("confidence", 0),
            barrier=self.state.barrier,
            language=parsed.get("language", self.state.language),
            signals=parsed.get("signals", []),
            action=action,
            latency_ms=int((_time.perf_counter() - t0) * 1000),
            used_fallback=used_fallback,
        )

    def filler(self) -> str:
        return FILLERS.get(self.state.language, FILLERS["en"])
