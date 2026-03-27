import logging
import time
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ── In-memory price cache ──────────────────────────────────────────────────────
# Structure: { coingecko_id: (price_usd, timestamp) }
_cache: dict[str, tuple[float, float]] = {}
CACHE_TTL = 60.0  # seconds before re-fetching

# ── Known contract address → coingecko_id mappings (EVM chains) ───────────────
# Extend this as needed or replace with a DB-backed lookup
CONTRACT_TO_COINGECKO_ID: dict[str, str] = {
    # Ethereum mainnet
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin",        # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "tether",           # USDT
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "wrapped-bitcoin",  # WBTC
    "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": "matic-network",    # MATIC
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "uniswap",          # UNI
    "0x514910771af9ca656af840dff83e8264ecf986ca": "chainlink",        # LINK
    "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "shiba-inu",        # SHIB
    "0x6b175474e89094c44da98b954eedeac495271d0f": "dai",              # DAI
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "weth",             # WETH
    # Add more as needed
}

# Native token by chain
NATIVE_TOKEN_IDS: dict[str, str] = {
    "ethereum": "ethereum",
    "polygon": "matic-network",
    "bsc": "binancecoin",
    "solana": "solana",
}


async def get_price(coingecko_id: str) -> float:
    """
    Fetch USD price for a single CoinGecko ID.
    Returns 0.0 on any failure — never raises.
    Results are cached for CACHE_TTL seconds.
    """
    now = time.monotonic()

    # Cache hit
    if coingecko_id in _cache:
        price, ts = _cache[coingecko_id]
        if now - ts < CACHE_TTL:
            return price

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{settings.COINGECKO_API_URL}/simple/price",
                params={
                    "ids": coingecko_id,
                    "vs_currencies": "usd",
                    "x_cg_demo_api_key": settings.COINGECKO_API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            price = float(data.get(coingecko_id, {}).get("usd", 0.0))
            _cache[coingecko_id] = (price, now)
            logger.debug(f"CoinGecko price [{coingecko_id}] = ${price}")
            return price

    except httpx.HTTPStatusError as e:
        # 429 = rate limited — return stale cache if available
        if e.response.status_code == 429:
            logger.warning("CoinGecko rate limit hit — using stale cache")
            if coingecko_id in _cache:
                return _cache[coingecko_id][0]
        else:
            logger.warning(f"CoinGecko HTTP {e.response.status_code} for {coingecko_id}")
    except Exception as e:
        logger.warning(f"CoinGecko fetch failed for {coingecko_id}: {e}")

    # Return stale cache on any error rather than 0
    if coingecko_id in _cache:
        logger.info(f"Returning stale cache for {coingecko_id}")
        return _cache[coingecko_id][0]

    return 0.0


async def get_prices(coingecko_ids: list[str]) -> dict[str, float]:
    """
    Batch fetch USD prices for multiple CoinGecko IDs in one API call.
    Returns { coingecko_id: price_usd }. Missing IDs default to 0.0.
    """
    if not coingecko_ids:
        return {}

    now = time.monotonic()
    results: dict[str, float] = {}
    to_fetch: list[str] = []

    # Split into cached and needs-fetch
    for cid in coingecko_ids:
        if cid in _cache:
            price, ts = _cache[cid]
            if now - ts < CACHE_TTL:
                results[cid] = price
                continue
        to_fetch.append(cid)

    if not to_fetch:
        return results

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{settings.COINGECKO_API_URL}/simple/price",
                params={
                    "ids": ",".join(to_fetch),
                    "vs_currencies": "usd",
                    "x_cg_demo_api_key": settings.COINGECKO_API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for cid in to_fetch:
                price = float(data.get(cid, {}).get("usd", 0.0))
                results[cid] = price
                _cache[cid] = (price, now)

    except httpx.HTTPStatusError as e:
        logger.warning(f"CoinGecko batch fetch HTTP {e.response.status_code}")
        # Fill from stale cache where possible
        for cid in to_fetch:
            results[cid] = _cache[cid][0] if cid in _cache else 0.0
    except Exception as e:
        logger.warning(f"CoinGecko batch fetch failed: {e}")
        for cid in to_fetch:
            results[cid] = _cache[cid][0] if cid in _cache else 0.0

    return results


async def get_price_for_contract(contract_address: str, chain: str = "ethereum") -> tuple[float, str]:
    """
    Resolve a contract address to a CoinGecko ID, then fetch its USD price.
    Falls back to the chain's native token if the contract isn't mapped.

    Returns (price_usd, coingecko_id).
    """
    addr = contract_address.lower()
    coingecko_id = CONTRACT_TO_COINGECKO_ID.get(addr)

    if not coingecko_id:
        # Try fetching from CoinGecko's contract endpoint
        coingecko_id = await _resolve_contract_via_api(addr, chain)

    if not coingecko_id:
        # Last resort: use native token price
        coingecko_id = NATIVE_TOKEN_IDS.get(chain.lower(), "ethereum")
        logger.debug(
            f"No mapping for contract {addr} — falling back to native token {coingecko_id}"
        )

    price = await get_price(coingecko_id)
    return price, coingecko_id


async def _resolve_contract_via_api(contract_address: str, chain: str) -> Optional[str]:
    """
    Ask CoinGecko to resolve a contract address to a coin ID.
    Uses the /coins/{platform}/contract/{address} endpoint.
    Result is cached in CONTRACT_TO_COINGECKO_ID for the process lifetime.
    """
    platform_map = {
        "ethereum": "ethereum",
        "polygon": "polygon-pos",
        "bsc": "binance-smart-chain",
        "solana": "solana",
    }
    platform = platform_map.get(chain.lower(), "ethereum")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{settings.COINGECKO_API_URL}/coins/{platform}/contract/{contract_address}",
                params={
                    "x_cg_demo_api_key": settings.COINGECKO_API_KEY,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                coingecko_id = data.get("id")
                if coingecko_id:
                    # Cache for future lookups
                    CONTRACT_TO_COINGECKO_ID[contract_address] = coingecko_id
                    logger.info(
                        f"Resolved contract {contract_address} → {coingecko_id} via API"
                    )
                    return coingecko_id
    except Exception as e:
        logger.warning(f"Contract resolution failed for {contract_address}: {e}")

    return None


async def get_token_info(coingecko_id: str) -> Optional[dict]:
    """
    Fetch full token metadata (name, symbol, market cap, 24h change etc.)
    from CoinGecko. Used by the /prices/{id} router endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.COINGECKO_API_URL}/coins/{coingecko_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "x_cg_demo_api_key": settings.COINGECKO_API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            market = data.get("market_data", {})
            return {
                "id": data.get("id"),
                "symbol": data.get("symbol", "").upper(),
                "name": data.get("name"),
                "price_usd": market.get("current_price", {}).get("usd", 0.0),
                "market_cap_usd": market.get("market_cap", {}).get("usd", 0.0),
                "volume_24h_usd": market.get("total_volume", {}).get("usd", 0.0),
                "price_change_24h_pct": market.get("price_change_percentage_24h", 0.0),
                "ath_usd": market.get("ath", {}).get("usd", 0.0),
                "image": data.get("image", {}).get("small"),
            }
    except Exception as e:
        logger.warning(f"get_token_info failed for {coingecko_id}: {e}")
        return None


def clear_cache() -> None:
    """Clear the in-memory price cache. Useful for testing."""
    _cache.clear()