import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.db import init_db
from src.webhooks import twilio as twilio_webhooks
from src.telephony.caller import place_outbound_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("voice-agent")

settings = get_settings()

app = FastAPI(title="ElevateBox Voice Agent")
app.include_router(twilio_webhooks.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.openrouter_model,
        "call_target_number": settings.call_target_number,
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "whatsapp_configured": bool(settings.whatsapp_access_token),
        "stt_configured": bool(settings.deepgram_api_key),
        "media_stream_enabled": settings.enable_media_stream and bool(settings.public_webhook_url),
    }


@app.post("/twilio/outbound")
async def trigger_outbound_call():
    try:
        result = place_outbound_call()
    except RuntimeError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=str(e))
    logger.info("Outbound call placed: %s", result)
    return result


@app.websocket("/media")
async def media_stream(ws: WebSocket):
    await ws.accept()
    call_sid = None
    try:
        while True:
            msg = await ws.receive_json()
            event = msg.get("event")
            if event == "start":
                start = msg.get("start", {})
                call_sid = start.get("customParameters", {}).get("call_sid") or start.get("callSid")
                logger.info("Media stream started for call %s", call_sid)
                init_db()
            elif event == "media":
                pass
            elif event == "stop":
                logger.info("Media stream stopped for call %s", call_sid)
                break
    except WebSocketDisconnect:
        logger.info("Media stream disconnected for call %s", call_sid)
