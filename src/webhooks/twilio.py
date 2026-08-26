from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from src.config import get_settings
from src.db import init_db, update_call_status, upsert_call
from src.telephony.caller import media_stream_wss_url

router = APIRouter(prefix="/twilio", tags=["twilio"])

STATUS_DURATION_FIELDS = {"completed": "CallDuration"}


async def verify_twilio_signature(request: Request) -> dict:
    s = get_settings()
    form = dict(await request.form())
    if not s.twilio_auth_token:
        return form
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")
    validator = RequestValidator(s.twilio_auth_token)
    url = str(request.url)
    public_base = s.public_webhook_url.rstrip("/")
    if public_base and not url.startswith(public_base):
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        url = f"{public_base}{path}{query}"
    if not validator.validate(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return form


@router.post("/voice")
async def voice(request: Request) -> Response:
    form = await verify_twilio_signature(request)
    call_sid = form.get("CallSid", "")
    to_number = form.get("To", "") or form.get("Called", "")
    from_number = form.get("From", "")

    init_db()
    upsert_call(call_sid, from_number or "unknown", status="in-progress")

    s = get_settings()
    resp = VoiceResponse()

    if s.enable_media_stream and s.public_webhook_url:
        connect = Connect()
        stream = Stream(url=media_stream_wss_url(call_sid))
        stream.parameter(name="call_sid", value=call_sid)
        stream.parameter(name="to_number", value=to_number)
        connect.append(stream)
        resp.append(connect)
    else:
        resp.say(
            "This is a test call from your AI agent. The voice loop is not enabled yet.",
            voice="Polly.Aditi",
            language="en-IN",
        )
        resp.hangup()

    return Response(content=str(resp), media_type="application/xml")


@router.post("/status")
async def status(request: Request) -> Response:
    form = await verify_twilio_signature(request)
    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "unknown")
    duration_raw = form.get("CallDuration")
    duration = int(duration_raw) if duration_raw and duration_raw.isdigit() else None

    if call_sid:
        update_call_status(call_sid, call_status, duration)
        if call_status == "completed":
            import asyncio

            asyncio.create_task(_finalize_call(call_sid))
    return Response(status_code=204)


async def _finalize_call(call_sid: str) -> None:
    import asyncio

    from src.db import get_call, get_turns, update_call_fields
    from src.whatsapp.dispatcher import send_final_package

    call = get_call(call_sid)
    if not call:
        return
    user_turns = [t["content"] for t in get_turns(call_sid) if t["role"] == "user"]
    if user_turns and not call.get("summary"):
        update_call_fields(call_sid, summary=". ".join(user_turns)[:800])
        call = get_call(call_sid)
    await asyncio.sleep(2)
    await send_final_package(call_sid, call)
