from datetime import datetime
from zoneinfo import ZoneInfo

from src.scheduler.parser import resolve_phrase, format_confirmation

IST = ZoneInfo("Asia/Kolkata")


def dt(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=IST)


def test_tomorrow_morning():
    resolved, amb = resolve_phrase("call me back tomorrow morning", now=dt(2026, 8, 24, 15, 0))
    assert not amb
    assert resolved == dt(2026, 8, 25, 10, 30)


def test_tomorrow_evening():
    resolved, amb = resolve_phrase("kal shaam ko call karna", now=dt(2026, 8, 24, 15, 0))
    assert not amb
    assert resolved == dt(2026, 8, 25, 19, 0)


def test_repu_udayam_telugu():
    resolved, amb = resolve_phrase("repu udayam call cheyandi", now=dt(2026, 8, 24, 20, 0))
    assert not amb
    assert resolved == dt(2026, 8, 25, 10, 30)


def test_explicit_time_afternoon():
    resolved, amb = resolve_phrase("call me at 4", now=dt(2026, 8, 24, 10, 0))
    assert not amb
    assert resolved == dt(2026, 8, 24, 16, 0)


def test_explicit_time_morning_stays_am():
    resolved, amb = resolve_phrase("call at 9 in the morning", now=dt(2026, 8, 24, 6, 0))
    assert not amb
    assert resolved == dt(2026, 8, 24, 9, 0)


def test_past_today_rolls_to_tomorrow():
    resolved, amb = resolve_phrase("call this afternoon", now=dt(2026, 8, 24, 18, 0))
    assert resolved == dt(2026, 8, 25, 14, 0)


def test_past_explicit_today_flags_ambiguous():
    resolved, amb = resolve_phrase("call today at 2", now=dt(2026, 8, 24, 15, 0))
    assert amb
    assert resolved == dt(2026, 8, 25, 14, 0)


def test_bare_weekday():
    resolved, amb = resolve_phrase("call me on wednesday", now=dt(2026, 8, 24, 10, 0))
    assert resolved.weekday() == 2
    assert resolved > dt(2026, 8, 24, 10, 0)


def test_vague_time_is_ambiguous():
    resolved, amb = resolve_phrase("kabhi bhi call kar lena", now=dt(2026, 8, 24, 10, 0))
    assert amb
    assert resolved is not None


def test_empty_phrase():
    resolved, amb = resolve_phrase("")
    assert resolved is None
    assert not amb


def test_word_number_hindi():
    resolved, amb = resolve_phrase("shaam ko paanch baje", now=dt(2026, 8, 24, 10, 0))
    assert not amb
    assert resolved.hour == 17


def test_confirmation_format():
    assert "IST" in format_confirmation(dt(2026, 8, 25, 10, 30))
