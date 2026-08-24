import asyncio
import logging

import httpx

from src.config import get_settings
from src.db import mark_action_sent, record_failed_action, update_call_fields, was_action_sent

logger = logging.getLogger("voice-agent.whatsapp")

GRAPH_URL = "https://graph.facebook.com/{version}/{phone_id}/messages"

MAX_ATTEMPTS = 3
BACKOFFS = [2, 8, 32]


def _url() -> str:
    s = get_settings()
    return GRAPH_URL.format(version=s.whatsapp_api_version, phone_id=s.whatsapp_phone_number_id)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().whatsapp_access_token}",
        "Content-Type": "application/json",
    }


async def _post(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(_url(), json=payload, headers=_headers())
        if r.status_code >= 400:
            raise RuntimeError(f"WhatsApp HTTP {r.status_code}: {r.text[:300]}")
        return r.json()


async def _send_with_retry(call_sid: str, action_type: str, payload: dict) -> bool:
    if was_action_sent(call_sid, action_type):
        return False
    if not mark_action_sent(call_sid, action_type):
        return False
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await _post(payload)
            logger.info("WhatsApp %s sent call=%s attempt=%d", action_type, call_sid, attempt)
            return True
        except Exception as e:
            last_error = str(e)
            logger.warning("WhatsApp %s failed call=%s attempt=%d: %s", action_type, call_sid, attempt, e)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFFS[attempt - 1])
    record_failed_action(call_sid, action_type, payload, last_error, MAX_ATTEMPTS)
    return False


def build_details_message(call) -> dict:
    s = get_settings()
    text = (
        "Hi! Priya here from the web studio — sending the e-commerce website details "
        "we just spoke about. I'll put together a quote based on your products and "
        "features and share it shortly. Save my number: "
        f"{s.applicant_mobile_number}"
    )
    return {"messaging_product": "whatsapp", "to": call.get("to_number", ""), "type": "text", "text": {"body": text}}


def build_final_message(call) -> dict:
    s = get_settings()
    summary = call.get("summary") or "our conversation about your e-commerce website"
    parts = [
        f"Hi! This is {s.applicant_name or 'the developer'} — thanks for taking my call about building your e-commerce website.",
        f"Quick recap of what we discussed: {summary}",
    ]
    if call.get("callback_at"):
        parts.append(f"I'll call you back at the time we fixed: {call['callback_at']} IST.")
    parts.append(f"You can reach me anytime on this number: {s.applicant_mobile_number}")
    components = []
    if s.resume_url:
        components.append({"type": "document", "document": {"link": s.resume_url, "filename": "resume.pdf"}})
    if s.architecture_image_url:
        components.append({"type": "image", "image": {"link": s.architecture_image_url}})
    msg = {"messaging_product": "whatsapp", "to": call.get("to_number", ""), "type": "text", "text": {"body": "\n\n".join(parts)}}
    return msg


def build_media_messages(call) -> list[dict]:
    s = get_settings()
    msgs = []
    if s.resume_url:
        msgs.append({
            "messaging_product": "whatsapp",
            "to": call.get("to_number", ""),
            "type": "document",
            "document": {"link": s.resume_url, "filename": "resume.pdf", "caption": "My resume"},
        })
    if s.architecture_image_url:
        msgs.append({
            "messaging_product": "whatsapp",
            "to": call.get("to_number", ""),
            "type": "image",
            "image": {"link": s.architecture_image_url, "caption": "How I built it — architecture"},
        })
    return msgs


async def dispatch_mid_call_actions(call_sid: str, turn_result, call: dict) -> None:
    action = turn_result.action
    is_hot = turn_result.classification == "hot"

    if action and action.get("type") == "book_callback":
        from src.scheduler.parser import resolve_phrase, is_ambiguous

        phrase = action.get("phrase", "")
        if phrase:
            resolved, ambiguous = resolve_phrase(phrase)
            if resolved and not ambiguous:
                update_call_fields(call_sid, callback_at=resolved.isoformat(), callback_phrase=phrase)
            else:
                update_call_fields(call_sid, callback_phrase=phrase)

    if action and action.get("type") == "send_whatsapp" or (is_hot and not was_action_sent(call_sid, "details")):
        if is_hot or (action and action.get("type") == "send_whatsapp"):
            payload = build_details_message(call)
            asyncio.create_task(_finalize_details(call_sid, payload))


async def _finalize_details(call_sid: str, payload: dict) -> None:
    sent = await _send_with_retry(call_sid, "details", payload)
    if sent:
        update_call_fields(call_sid, whatsapp_sent=1)


async def send_final_package(call_sid: str, call: dict) -> None:
    if was_action_sent(call_sid, "final_package"):
        return
    if not mark_action_sent(call_sid, "final_package"):
        return
    try:
        await _post(build_final_message(call))
        for msg in build_media_messages(call):
            await _post(msg)
        update_call_fields(call_sid, followup_sent=1)
        logger.info("Final WhatsApp package sent call=%s", call_sid)
    except Exception as e:
        record_failed_action(call_sid, "final_package", build_final_message(call), str(e), 1)
