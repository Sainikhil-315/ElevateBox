from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["call_target_number"] == "7093647471"


def test_voice_twiml_without_stream():
    r = client.post("/twilio/voice", data={"CallSid": "CA123", "From": "+917093647471", "To": "+14155551234"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    text = r.text
    assert "<Response>" in text
    assert "<Say" in text
    assert "not enabled yet" in text
    assert "<Connect>" not in text


def test_voice_twiml_with_stream():
    from src.config import get_settings
    get_settings().enable_media_stream = True
    get_settings().public_webhook_url = "https://example.up.railway.app"
    try:
        r = client.post("/twilio/voice", data={"CallSid": "CA456", "From": "+917093647471"})
        assert "<Connect>" in r.text
        assert "wss://example.up.railway.app/media?call_sid=CA456" in r.text
        assert "CA456" in r.text
    finally:
        get_settings().enable_media_stream = False
        get_settings().public_webhook_url = ""


def test_status_updates_call():
    client.post("/twilio/voice", data={"CallSid": "CA789", "From": "+917093647471"})
    r = client.post(
        "/twilio/status",
        data={"CallSid": "CA789", "CallStatus": "completed", "CallDuration": "42"},
    )
    assert r.status_code == 204


def test_outbound_requires_credentials():
    r = client.post("/twilio/outbound")
    assert r.status_code in (500, 503)


def test_media_ws_accepts_events():
    with client.websocket_connect("/media") as ws:
        ws.send_json({"event": "start", "start": {"customParameters": {"call_sid": "CAWS1"}}})
        ws.send_json({"event": "media", "media": {"payload": "dGVzdA=="}})
        ws.send_json({"event": "stop"})
