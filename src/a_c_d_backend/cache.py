import logging
from typing import Optional

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)

WALLET_CACHE_TTL = 3600

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        # Check if we have a full Redis URL in settings (recommended for cloud)
        if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
            _redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        else:
            _redis = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True,
            )
    return _redis


async def get_wallet_id(address: str) -> Optional[str]:
    try:
        return await get_redis().get(f"wallet:{address}")
    except Exception as e:
        logger.warning(f"Redis get_wallet_id error: {e}")
        return None


async def set_wallet_id(address: str, wallet_id: str) -> None:
    try:
        await get_redis().set(f"wallet:{address}", wallet_id, ex=WALLET_CACHE_TTL)
    except Exception as e:
        logger.warning(f"Redis set_wallet_id error: {e}")


async def invalidate_wallet(address: str) -> None:
    try:
        await get_redis().delete(f"wallet:{address}")
    except Exception as e:
        logger.warning(f"Redis invalidate_wallet error: {e}")


async def close():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None