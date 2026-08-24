from urllib.parse import urlencode

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from main import app

client = TestClient(app)


def signed_form(path: str, form: dict) -> dict:
    s_form = dict(form)
    validator = RequestValidator(_token())
    signature = validator.compute_signature(f"http://testserver{path}", s_form)
    s_form["__signature__"] = signature
    return s_form


def _token() -> str:
    from src.config import get_settings
    return get_settings().twilio_auth_token or "test-token"


def post_signed(path: str, form: dict):
    s_form = dict(form)
    from src.config import get_settings
    s = get_settings()
    url = f"http://testserver{path}"
    if s.public_webhook_url:
        url = s.public_webhook_url.rstrip("/") + path
    token = s.twilio_auth_token
    if token:
        validator = RequestValidator(token)
        headers = {"X-Twilio-Signature": validator.compute_signature(url, s_form)}
        return client.post(path, data=s_form, headers=headers)
    return client.post(path, data=s_form)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["call_target_number"] == "7093647471"


def test_voice_twiml_without_stream():
    r = post_signed("/twilio/voice", {"CallSid": "CA123", "From": "+917093647471", "To": "+14155551234"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    text = r.text
    assert "<Response>" in text
    assert "<Say" in text
    assert "<Connect>" not in text


def test_voice_twiml_with_stream():
    from src.config import get_settings
    get_settings().enable_media_stream = True
    get_settings().public_webhook_url = "https://example.up.railway.app"
    try:
        r = post_signed("/twilio/voice", {"CallSid": "CA456", "From": "+917093647471"})
        assert "<Connect>" in r.text
        assert "wss://example.up.railway.app/media?call_sid=CA456" in r.text
        assert "CA456" in r.text
    finally:
        get_settings().enable_media_stream = False
        get_settings().public_webhook_url = ""


def test_status_updates_call():
    post_signed("/twilio/voice", {"CallSid": "CA789", "From": "+917093647471"})
    r = post_signed(
        "/twilio/status",
        {"CallSid": "CA789", "CallStatus": "completed", "CallDuration": "42"},
    )
    assert r.status_code == 204


def test_rejects_unsigned_when_token_present():
    from src.config import get_settings
    if not get_settings().twilio_auth_token:
        return
    r = client.post("/twilio/voice", data={"CallSid": "CAX", "From": "+917093647471"})
    assert r.status_code == 403


def test_outbound_requires_public_url(monkeypatch):
    from src.config import get_settings
    original = get_settings().public_webhook_url
    get_settings().public_webhook_url = ""
    try:
        r = client.post("/twilio/outbound")
        assert r.status_code in (500, 503)
    finally:
        get_settings().public_webhook_url = original


def test_media_ws_accepts_events(monkeypatch):
    class StubDeepgram:
        def __init__(self, *a, **k):
            pass

        async def start(self):
            pass

        async def send_audio(self, payload):
            pass

        async def transcripts(self):
            yield None
            return

        async def finish(self):
            pass

    import src.telephony.media_handler as mh
    monkeypatch.setattr(mh, "DeepgramStream", StubDeepgram)

    with client.websocket_connect("/media") as ws:
        ws.send_json({"event": "start", "streamSid": "MS1", "start": {"streamSid": "MS1", "customParameters": {"call_sid": "CAWS1"}}})
        ws.send_json({"event": "media", "media": {"payload": "dGVzdA=="}})
        ws.send_json({"event": "stop"})
