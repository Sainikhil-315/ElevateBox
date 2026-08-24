from src.config import get_settings
from src.whatsapp.dispatcher import build_details_message, build_final_message


def test_details_message_contains_number():
    s = get_settings()
    s.applicant_mobile_number = "7093647471"
    msg = build_details_message({"to_number": "+917093647471"})
    assert msg["to"] == "+917093647471"
    assert "7093647471" in msg["text"]["body"]
    assert msg["messaging_product"] == "whatsapp"


def test_final_message_has_context_and_number():
    s = get_settings()
    s.applicant_name = "Sainikhil"
    s.applicant_mobile_number = "7093647471"
    call = {
        "to_number": "+918688664337",
        "summary": "sells clothes, wants online payments, budget around 20k",
        "callback_at": "2026-08-25T10:30:00+05:30",
    }
    msg = build_final_message(call)
    body = msg["text"]["body"]
    assert "Sainikhil" in body
    assert "7093647471" in body
    assert "sells clothes" in body
    assert "2026-08-25T10:30" in body


def test_final_message_without_callback():
    call = {"to_number": "+917093647471", "summary": "just browsing"}
    msg = build_final_message(call)
    assert "call you back at the time" not in msg["text"]["body"]
    assert "just browsing" in msg["text"]["body"]
