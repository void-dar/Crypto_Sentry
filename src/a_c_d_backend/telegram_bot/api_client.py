"""
Internal HTTP client the bot uses to talk to our own FastAPI backend.
All bot commands go through the REST API — no direct DB access from the bot.
This keeps auth, validation, and business logic in one place.
"""

import logging
from typing import Any, Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.BASE_URL


class BotAPIClient:
    """
    Thin async HTTP client wrapping our own FastAPI endpoints.
    Each method corresponds to one API call.
    Bearer token is passed per-call (stored in bot user_data).
    """

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=10.0,
        )

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def login(self, email: str, password: str) -> Optional[dict]:
        try:
            resp = await self._client.post(
                "/auth/login",
                json={"email": email, "password": password},
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"login error: {e}")
            return None

    async def register(self, username: str, email: str, password: str) -> Optional[dict]:
        try:
            resp = await self._client.post(
                "/auth/register",
                json={"username": username, "email": email, "password": password},
            )
            if resp.status_code == 201:
                return resp.json()
            return {"error": resp.json().get("detail", "Registration failed")}
        except Exception as e:
            logger.error(f"register error: {e}")
            return None

    async def get_me(self, token: str) -> Optional[dict]:
        try:
            resp = await self._client.get("/auth/me", headers=self._headers(token))
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"get_me error: {e}")
            return None

    async def link_telegram(self, token: str, tg_chat_id: str) -> bool:
        try:
            resp = await self._client.post(
                "/auth/link-telegram",
                json={"tg_chat_id": tg_chat_id},
                headers=self._headers(token),
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"link_telegram error: {e}")
            return False

    # ── Wallets ───────────────────────────────────────────────────────────────

    async def list_wallets(self, token: str) -> list[dict]:
        try:
            resp = await self._client.get("/wallets/", headers=self._headers(token))
            return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.error(f"list_wallets error: {e}")
            return []

    async def add_wallet(
        self, token: str, address: str, chain: str, label: Optional[str] = None
    ) -> Optional[dict]:
        try:
            resp = await self._client.post(
                "/wallets/",
                json={"address": address, "chain": chain, "label": label},
                headers=self._headers(token),
            )
            if resp.status_code == 201:
                return resp.json()
            return {"error": resp.json().get("detail", "Failed to add wallet")}
        except Exception as e:
            logger.error(f"add_wallet error: {e}")
            return None

    async def remove_wallet(self, token: str, wallet_id: str) -> bool:
        try:
            resp = await self._client.delete(
                f"/wallets/{wallet_id}", headers=self._headers(token)
            )
            return resp.status_code == 204
        except Exception as e:
            logger.error(f"remove_wallet error: {e}")
            return False

    # ── Transactions ──────────────────────────────────────────────────────────

    async def get_transactions(
        self,
        token: str,
        wallet_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Optional[dict]:
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if wallet_id:
                params["wallet_id"] = wallet_id
            resp = await self._client.get(
                "/transactions/",
                params=params,
                headers=self._headers(token),
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"get_transactions error: {e}")
            return None

    # ── Alerts ────────────────────────────────────────────────────────────────

    async def list_alerts(self, token: str, wallet_id: str) -> list[dict]:
        try:
            resp = await self._client.get(
                f"/wallets/{wallet_id}/alerts/",
                headers=self._headers(token),
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.error(f"list_alerts error: {e}")
            return []

    async def add_alert(
        self,
        name: str,
        token: str,
        wallet_id: str,
        alert_type: str,
        threshold_amount: Optional[float] = None,
        token_symbol: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            body: dict[str, Any] = {"type": alert_type, "name": name}
            if threshold_amount is not None:
                body["threshold_amount"] = threshold_amount
            if token_symbol:
                body["token_symbol"] = token_symbol
            resp = await self._client.post(
                f"/wallets/{wallet_id}/alerts/",
                json=body,
                headers=self._headers(token),
            )
            if resp.status_code == 201:
                return resp.json()
            return {"error": resp.json().get("detail", "Failed to add alert")}
        except Exception as e:
            logger.error(f"add_alert error: {e}")
            return None

    async def delete_alert(self, token: str, wallet_id: str, rule_id: str) -> bool:
        try:
            resp = await self._client.delete(
                f"/wallets/{wallet_id}/alerts/{rule_id}",
                headers=self._headers(token),
            )
            return resp.status_code == 204
        except Exception as e:
            logger.error(f"delete_alert error: {e}")
            return False

    # ── Prices ────────────────────────────────────────────────────────────────

    async def get_price(self, token: str, coingecko_id: str) -> Optional[float]:
        try:
            resp = await self._client.get(
                f"/prices/{coingecko_id}",
                headers=self._headers(token),
            )
            if resp.status_code == 200:
                return resp.json().get("price_usd")
            return None
        except Exception as e:
            logger.error(f"get_price error: {e}")
            return None

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def get_subscription(self, token: str) -> Optional[dict]:
        try:
            resp = await self._client.get(
                "/subscriptions/me", headers=self._headers(token)
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"get_subscription error: {e}")
            return None

    async def get_plans(self) -> list[dict]:
        try:
            resp = await self._client.get("/subscriptions/plans")
            return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.error(f"get_plans error: {e}")
            return []

    async def get_checkout_url(
        self, token: str, plan_id: str, provider: str = "stripe"
    ) -> Optional[str]:
        try:
            resp = await self._client.post(
                f"/subscriptions/{provider}/checkout/{plan_id}",
                headers=self._headers(token),
            )
            if resp.status_code == 200:
                return resp.json().get("checkout_url")
            return None
        except Exception as e:
            logger.error(f"get_checkout_url error: {e}")
            return None

    # ── Dashboard ─────────────────────────────────────────────────────────────

    async def get_activity(self, token: str) -> Optional[dict]:
        try:
            resp = await self._client.get(
                "/users/me/activity", headers=self._headers(token)
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"get_activity error: {e}")
            return None

    async def close(self):
        await self._client.aclose()


# Singleton — shared across all handlers
api = BotAPIClient()