import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "somvaar": 0, "mangalvaar": 1, "budhvaar": 2, "guruvaar": 3, "guruvar": 3,
    "shukravaar": 4, "shanivaar": 5, "ravivaar": 6,
    "somaaram": 0,
}

DAYPART_TIMES = {
    "morning": (10, 30),
    "subah": (10, 30),
    "udayam": (10, 30),
    "afternoon": (14, 0),
    "dopahar": (14, 0),
    "madhyahnam": (14, 0),
    "evening": (19, 0),
    "shaam": (19, 0),
    "saayamtram": (19, 0),
    "night": (20, 30),
    "raat": (20, 30),
    "ratri": (20, 30),
    "tonight": (20, 30),
}

MINUTES_IN_HOUR = 60
PAST_BUFFER_MIN = 30

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chah": 6, "cheh": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "okati": 1, "rendu": 2, "moodu": 3, "nalugu": 4, "aidu": 5, "aaru": 6,
    "yedu": 7, "enimidi": 8, "tommidi": 9, "padi": 10, "padakondu": 11, "panendu": 12,
}

NUM_RE = re.compile(r"\b(\d{1,2})\b")
WORD_NUM_RE = re.compile(r"\b(" + "|".join(WORD_NUMBERS.keys()) + r")\b", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(IST)


def _daypart_hour(phrase: str, default: tuple[int, int]) -> tuple[int, int]:
    p = phrase.lower()
    for key, val in DAYPART_TIMES.items():
        if key in p:
            return val
    return default


def _extract_hour(phrase: str) -> tuple[int, bool] | None:
    p = phrase.lower()
    explicit_pm = bool(re.search(r"\b(pm|p\.m|evening|shaam|saayam|raat|night|afternoon|dopahar)\b", p))
    explicit_am = bool(re.search(r"\b(am|a\.m|morning|subah|udayam)\b", p))

    m = NUM_RE.search(p)
    hour = None
    if m:
        hour = int(m.group(1))
    else:
        mw = WORD_NUM_RE.search(p)
        if mw:
            hour = WORD_NUMBERS[mw.group(1).lower()]
    if hour is None or hour > 12:
        return None

    if explicit_am and not explicit_pm:
        hour = hour % 12
    elif explicit_pm and not explicit_am:
        hour = hour % 12 + (12 if hour != 12 else 0)
    else:
        if hour < 7:
            hour += 12
    return hour, True


def _next_weekday(phrase: str, now: datetime) -> datetime | None:
    p = phrase.lower()
    for name, idx in WEEKDAYS.items():
        if name in p:
            days_ahead = (idx - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return now + timedelta(days=days_ahead)
    return None


def resolve_phrase(phrase: str, now: datetime | None = None) -> tuple[datetime | None, bool]:
    if not phrase or not phrase.strip():
        return None, False

    now = now or _now()
    p = phrase.lower().strip()

    base_day = now
    has_day = False
    if "day after tomorrow" in p or "parso" in p or "ellundi" in p:
        base_day = now + timedelta(days=2)
        has_day = True
    elif "tomorrow" in p or "kal" in p or "repu" in p:
        base_day = now + timedelta(days=1)
        has_day = True
    elif "today" in p or "aaj" in p or "ee roju" in p or "i roju" in p:
        base_day = now
        has_day = True
    else:
        wd = _next_weekday(p, now)
        if wd:
            base_day = wd
            has_day = True

    hour_info = _extract_hour(p)
    ambiguous = False

    if hour_info:
        hour, _ = hour_info
        minute = 0
        m_min = re.search(r":(\d{2})|\b(\d{1,2})[:.](\d{2})\b", p)
        if m_min:
            groups = [g for g in m_min.groups() if g]
            minute = int(groups[-1]) if groups else 0
    else:
        hour, minute = _daypart_hour(p, (10, 30))
        if not has_day:
            ambiguous = True

    candidate = base_day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if candidate <= now + timedelta(minutes=PAST_BUFFER_MIN):
        if "today" in p or "aaj" in p or "ee roju" in p:
            ambiguous = True
        candidate = (candidate + timedelta(days=1)).replace(hour=hour, minute=minute)

    return candidate, ambiguous


def format_confirmation(dt: datetime) -> str:
    return dt.strftime("%A, %d %b at %H:%M IST")


def is_ambiguous(result: tuple[datetime | None, bool]) -> bool:
    return result[1]
