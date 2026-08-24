from urllib.parse import urlencode

from twilio.rest import Client

from src.config import get_settings
from src.db import init_db, upsert_call


def get_client() -> Client:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        raise RuntimeError("Twilio credentials not configured")
    return Client(s.twilio_account_sid, s.twilio_auth_token)


def media_stream_wss_url(call_sid: str | None = None) -> str:
    s = get_settings()
    base = s.public_webhook_url.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    params = f"?{urlencode({'call_sid': call_sid})}" if call_sid else ""
    return f"{ws_base}/media{params}"


def place_outbound_call(to_number: str | None = None) -> dict:
    s = get_settings()
    to = to_number or s.call_target_number
    if not s.public_webhook_url:
        raise RuntimeError("PUBLIC_WEBHOOK_URL not configured")
    client = get_client()

    voice_url = f"{s.public_webhook_url.rstrip('/')}/twilio/voice"
    status_url = f"{s.public_webhook_url.rstrip('/')}/twilio/status"

    call = client.calls.create(
        to=to,
        from_=s.twilio_phone_number,
        url=voice_url,
        method="POST",
        status_callback=status_url,
        status_callback_event=["completed", "busy", "no-answer", "failed", "canceled"],
        timeout=30,
    )

    init_db()
    upsert_call(call.sid, to, status=call.status or "queued")
    return {"call_sid": call.sid, "to": to, "status": call.status}
