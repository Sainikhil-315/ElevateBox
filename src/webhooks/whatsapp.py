import logging

from fastapi import APIRouter, Query, Request, Response

from src.config import get_settings

logger = logging.getLogger("voice-agent.whatsapp")

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def verify(
    request: Request,
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    s = get_settings()
    expected = getattr(s, "whatsapp_verify_token", "") or ""
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == expected:
        return Response(content=hub_challenge or "", status_code=200)
    return Response(status_code=403)


@router.post("/webhook")
async def inbound(request: Request):
    body = await request.json()
    logger.info("WhatsApp webhook: %s", body)
    return Response(status_code=200)
