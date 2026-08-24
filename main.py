import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.db import init_db
from src.webhooks import twilio as twilio_webhooks
from src.webhooks import whatsapp as whatsapp_webhooks
from src.telephony.caller import place_outbound_call
from src.telephony.media_handler import MediaSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("voice-agent")

settings = get_settings()

app = FastAPI(title="ElevateBox Voice Agent")
app.include_router(twilio_webhooks.router)
app.include_router(whatsapp_webhooks.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.openrouter_model,
        "llm_base_url": settings.llm_base_url,
        "call_target_number": settings.call_target_number,
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "whatsapp_configured": bool(settings.whatsapp_access_token),
        "stt_configured": bool(settings.deepgram_api_key),
        "tts_configured": bool(settings.google_tts_api_key or settings.google_application_credentials),
        "llm_configured": bool(settings.gemini_api_key or settings.openrouter_api_key),
        "media_stream_enabled": settings.enable_media_stream and bool(settings.public_webhook_url),
    }


@app.post("/twilio/outbound")
async def trigger_outbound_call():
    try:
        result = place_outbound_call()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    logger.info("Outbound call placed: %s", result)
    return result


@app.websocket("/media")
async def media_stream(ws: WebSocket):
    await ws.accept()
    session = MediaSession(ws)
    try:
        await session.run()
    except WebSocketDisconnect:
        logger.info("Media WS disconnected call=%s", session.call_sid)
