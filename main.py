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
    from src.llm.client import _resolve_provider

    try:
        key, model, base_url = _resolve_provider()
        llm_ok = bool(key)
    except Exception:
        model, base_url, llm_ok = "?", "?", False
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": model,
        "llm_base_url": base_url,
        "call_target_number": settings.call_target_number,
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "whatsapp_configured": bool(settings.whatsapp_access_token),
        "stt_configured": bool(settings.deepgram_api_key),
        "tts_configured": bool(settings.google_tts_api_key or settings.google_application_credentials),
        "llm_configured": llm_ok,
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

@app.post("/whatsapp/test-full")
async def test_whatsapp_full():
    from src.whatsapp.dispatcher import _post
    from src.config import get_settings

    s = get_settings()

    results = []

    # 1. Text
    text_payload = {
        "messaging_product": "whatsapp",
        "to": "917093647471",
        "type": "text",
        "text": {
            "body": (
                f"Hi! This is {s.applicant_name}.\n\n"
                "Here are the details we discussed.\n\n"
                f"You can reach me on {s.applicant_mobile_number}"
            )
        }
    }

    results.append({
        "type": "text",
        "response": await _post(text_payload)
    })

    # 2. Resume
    if s.resume_url:
        resume_payload = {
            "messaging_product": "whatsapp",
            "to": "917093647471",
            "type": "document",
            "document": {
                "link": s.resume_url,
                "filename": "resume.pdf",
                "caption": "My resume"
            }
        }

        results.append({
            "type": "resume",
            "response": await _post(resume_payload)
        })

    # 3. Architecture image
    if s.architecture_image_url:
        image_payload = {
            "messaging_product": "whatsapp",
            "to": "917093647471",
            "type": "image",
            "image": {
                "link": s.architecture_image_url,
                "caption": "How I built it — architecture"
            }
        }

        results.append({
            "type": "architecture",
            "response": await _post(image_payload)
        })

    return {
        "applicant_name": s.applicant_name,
        "applicant_mobile_number": s.applicant_mobile_number,
        "resume_url": s.resume_url,
        "architecture_image_url": s.architecture_image_url,
        "results": results
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
