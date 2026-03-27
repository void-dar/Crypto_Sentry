import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.main import get_session as get_db
from ..worker import process_tx

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

ALCHEMY_WEBHOOK_SECRET = os.getenv("ALCHEMY_WEBHOOK_SECRET", "")


def _verify_alchemy_signature(body: bytes, signature: str) -> bool:
    """
    Alchemy signs the raw request body with HMAC-SHA256.
    Header: X-Alchemy-Signature
    Skip verification only in dev (secret not set).
    """
    if not ALCHEMY_WEBHOOK_SECRET:
        logger.warning("ALCHEMY_WEBHOOK_SECRET not set — skipping signature check")
        return True
    expected = hmac.new(
        ALCHEMY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/alchemy")
async def alchemy_webhook(
    request: Request,
    x_alchemy_signature: str = Header("", alias="X-Alchemy-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Receives Alchemy Address Activity webhook events.
    Replaces the WebSocket listener entirely — Alchemy pushes to us,
    we don't need a persistent outbound connection.

    Each 'activity' entry in the payload is one on-chain event.
    We process them concurrently with asyncio.gather.
    """
    body = await request.body()

    if not _verify_alchemy_signature(body, x_alchemy_signature):
        logger.warning("Rejected Alchemy webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event", {})
    activity_list = event.get("activity", [])

    if not activity_list:
        return {"status": "ok", "processed": 0}

    # ── Normalise Alchemy activity → our tx dict format ──────────────────────
    import asyncio

    async def _handle_activity(activity: dict):
        """Map one Alchemy activity object to process_tx's expected shape."""
        tx = {
            "hash": activity.get("hash", ""),
            "from": (activity.get("fromAddress") or "").lower(),
            "to": (activity.get("toAddress") or "").lower(),
            # Alchemy gives ETH value as decimal float, not hex wei
            # We re-encode to hex so process_tx's int(..., 16) / 1e18 works
            "value": hex(int(float(activity.get("value", 0)) * 1e18)),
            "blockNumber": hex(activity.get("blockNum", 0))
            if isinstance(activity.get("blockNum"), int)
            else activity.get("blockNum", "0x0"),
            # Pass the full activity dict as raw_data
            "_raw": activity,
        }
        if tx["hash"]:
            await process_tx(tx)

    await asyncio.gather(*[_handle_activity(a) for a in activity_list])

    return {"status": "ok", "processed": len(activity_list)}