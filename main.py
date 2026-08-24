from fastapi import FastAPI

from src.config import get_settings

settings = get_settings()

app = FastAPI(title="ElevateBox Voice Agent")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.openrouter_model,
        "call_target_number": settings.call_target_number,
        "twilio_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "whatsapp_configured": bool(settings.whatsapp_access_token),
        "stt_configured": bool(settings.deepgram_api_key),
    }


@app.post("/twilio/outbound")
async def trigger_outbound_call():
    raise NotImplementedError("Phase 1: Twilio outbound dialing")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
