import asyncio
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

FREE_TIER_DELAY_SECONDS = 30

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def _send(chat_id: str, message: str) -> bool:
    if not settings.BOT_TOKEN or not chat_id:
        return False
    try:
        resp = await get_http_client().post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"Telegram send failed for {chat_id}: {e}")
        return False


async def send_alert(user, message: str) -> None:
    from ..db.models import Tier

    is_premium = user.tier in (Tier.PRO, Tier.STARTER)

    if not is_premium:
        await asyncio.sleep(FREE_TIER_DELAY_SECONDS)

    if user.tg_chat_id:
        await _send(user.tg_chat_id, message)


async def close():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()