import asyncio
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..db.models import AlertLog, AlertRule, AlertType, Transaction, TrackedWallet, User
from ..services.telegram import send_alert, _send

logger = logging.getLogger(__name__)


# ── Message builders ───────────────────────────────────────────────────────────

def _build_whale_message(tx: Transaction, wallet: TrackedWallet) -> str:
    """Used for large_tx and token_transfer rules — emphasises amount/symbol."""
    chain = wallet.chain.value.upper()
    direction = "📥 IN" if tx.direction.value == "in" else "📤 OUT"
    usd_str = f" (~${tx.usd_value:,.2f})" if tx.usd_value else ""

    return (
        f"🐳 <b>Whale Alert — {tx.token_symbol.upper()}</b> [{chain}] {direction}\n"
        f"Amount: <b>{tx.amount:.6f} {tx.token_symbol}</b>{usd_str}\n"
        f"From: <code>{tx.from_address}</code>\n"
        f"To:   <code>{tx.to_address}</code>\n"
        f"Tx:   <code>{tx.tx_hash}</code>\n"
        f"🔗 <a href='https://etherscan.io/tx/{tx.tx_hash}'>View on Etherscan</a>"
    )


def _build_wallet_message(tx: Transaction, wallet: TrackedWallet) -> str:
    """Used for wallet_activity rules — emphasises address and ETH value."""
    chain = wallet.chain.value.upper()
    usd_str = f"(~${tx.usd_value:,.0f})" if tx.usd_value else ""

    return (
        f"🔔 <b>Wallet Activity</b>\n"
        f"Chain: <code>{chain}</code>\n"
        f"Address: <code>{wallet.address}</code>\n"
        f"Value: <b>{tx.amount:.4f} {tx.token_symbol}</b> {usd_str}\n"
        f"Tx: <code>{tx.tx_hash}</code>\n"
        f"🔗 <a href='https://etherscan.io/tx/{tx.tx_hash}'>View on Etherscan</a>"
    )


# ── Targeted alert senders (use these when you have a chat_id directly) ────────

async def send_wallet_alert(
    chat_id: str,
    address: str,
    tx_hash: str,
    chain: str,
    value_eth: float,
    usd_value: float,
) -> None:
    """
    Send a wallet activity alert to a specific chat_id.
    Use this when you have the chat_id in hand (e.g. from a webhook handler)
    and don't need to go through the rule engine.
    """
    msg = (
        f"🔔 <b>Wallet Activity</b>\n"
        f"Chain: <code>{chain}</code>\n"
        f"Address: <code>{address}</code>\n"
        f"Value: <b>{value_eth:.4f} ETH</b> (~${usd_value:,.0f})\n"
        f"Tx: <code>{tx_hash}</code>\n"
        f"🔗 <a href='https://etherscan.io/tx/{tx_hash}'>View on Etherscan</a>"
    )
    await _send(chat_id, msg)


async def send_whale_alert(
    chat_id: str,
    address: str,
    tx_hash: str,
    symbol: str,
    chain: str,
    usd_value: float,
) -> None:
    """
    Send a whale alert to a specific chat_id.
    Use this when you have the chat_id in hand and don't need the rule engine.
    """
    msg = (
        f"🐳 <b>Whale Alert — {symbol.upper()}</b>\n"
        f"Chain: <code>{chain}</code>\n"
        f"From/To: <code>{address}</code>\n"
        f"Amount: ~<b>${usd_value:,.0f}</b>\n"
        f"Tx: <code>{tx_hash}</code>\n"
        f"🔗 <a href='https://etherscan.io/tx/{tx_hash}'>View on Etherscan</a>"
    )
    await _send(chat_id, msg)


# ── Rule engine ────────────────────────────────────────────────────────────────

async def run_alert_for_tx(tx: Transaction, db: AsyncSession) -> None:
    """
    Evaluate all active AlertRules for the wallet that owns this transaction.
    Routes to the correct message builder based on rule type.
    Fires Telegram alerts and writes AlertLog rows for triggered rules.
    """
    rules_result = await db.execute(
        select(AlertRule).where(
            AlertRule.wallet_id == tx.wallet_id,
            AlertRule.is_active == True,  # noqa: E712
        )
    )
    rules = rules_result.scalars().all()

    if not rules:
        return

    wallet = await db.get(TrackedWallet, tx.wallet_id)
    if not wallet:
        logger.warning(f"Wallet {tx.wallet_id} not found for tx {tx.tx_hash}")
        return

    # Explicit fetch — never traverse wallet.user across an await boundary
    user = await db.get(User, wallet.user_id)
    if not user or not user.is_active:
        return

    logs_to_add = []

    for rule in rules:
        triggered = False
        message = ""

        if rule.type == AlertType.LARGE_TX:
            if rule.threshold_amount and tx.amount >= rule.threshold_amount:
                triggered = True
                message = _build_whale_message(tx, wallet)

        elif rule.type == AlertType.TOKEN_TRANSFER:
            if rule.token_symbol and tx.token_symbol == rule.token_symbol:
                triggered = True
                message = _build_whale_message(tx, wallet)

        elif rule.type == AlertType.WALLET_ACTIVITY:
            triggered = True
            message = _build_wallet_message(tx, wallet)

        if not triggered:
            continue

        # Non-blocking — doesn't hold up the DB commit
        asyncio.create_task(send_alert(user, message))

        if rule.webhook_url:
            asyncio.create_task(_fire_webhook(rule.webhook_url, tx, message))

        logs_to_add.append(
            AlertLog(
                wallet_id=tx.wallet_id,
                transaction_id=tx.id,
                message=message,
            )
        )

    if logs_to_add:
        db.add_all(logs_to_add)
        await db.commit()
        logger.info(f"Fired {len(logs_to_add)} alert(s) for tx {tx.tx_hash}")


# ── Custom webhook dispatcher ──────────────────────────────────────────────────

async def _fire_webhook(url: str, tx: Transaction, message: str) -> None:
    """POST alert payload to a user-configured webhook URL. Non-blocking."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                url,
                json={
                    "tx_hash": tx.tx_hash,
                    "from": tx.from_address,
                    "to": tx.to_address,
                    "amount": str(tx.amount),
                    "token": tx.token_symbol,
                    "usd_value": str(tx.usd_value or 0),
                    "message": message,
                },
            )
    except Exception as e:
        logger.warning(f"Custom webhook {url} failed: {e}")