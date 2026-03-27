import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import select

from .db.main import Session
from .db.models import Transaction, TrackedWallet, TxDirection
from .services.alert import run_alert_for_tx
from .services.coingecko import (
    CONTRACT_TO_COINGECKO_ID,
    NATIVE_TOKEN_IDS,
    get_price,
    get_price_for_contract,
)
from .cache import get_wallet_id, set_wallet_id

logger = logging.getLogger(__name__)


async def process_tx(tx: dict) -> None:
    """
    Entry point called by the webhook receiver for each new transaction dict.

    Lookup order for wallet ownership:
      1. Redis cache  (sub-millisecond)
      2. DB query     (fallback, result written back to Redis)

    USD value is resolved via CoinGecko for both native tokens and ERC-20s.
    """
    tx_hash: str = tx.get("hash", "")
    if not tx_hash:
        logger.warning("process_tx called with tx missing 'hash' field")
        return

    from_addr = (tx.get("from") or "").lower()
    to_addr = (tx.get("to") or "").lower()

    if not from_addr and not to_addr:
        return

    # ✅ Session — not Session (sync) and not get_db (generator)
    async with Session() as db:

        # ── 1. Resolve wallet_id ──────────────────────────────────────────────

        wallet_id: UUID | None = None
        matched_address: str | None = None

        for addr in filter(None, [to_addr, from_addr]):
            cached = await get_wallet_id(addr)
            if cached:
                wallet_id = UUID(cached)
                matched_address = addr
                break

        if not wallet_id:
            candidates = [a for a in [to_addr, from_addr] if a]
            result = await db.exec(   # ✅ db.exec, not db.exec
                select(TrackedWallet).where(
                    TrackedWallet.address.in_(candidates),
                    TrackedWallet.is_active == True,  # noqa: E712
                )
            )
            wallet = result.scalars().first()
            if wallet:
                wallet_id = wallet.id
                matched_address = wallet.address.lower()
                await set_wallet_id(matched_address, str(wallet_id))

        if not wallet_id or not matched_address:
            return

        # ── 2. Deduplication ──────────────────────────────────────────────────

        existing = await db.exec(     # ✅ db.exec, not db.exec
            select(Transaction).where(Transaction.tx_hash == tx_hash)
        )
        if existing.scalar_one_or_none():
            logger.debug(f"Duplicate tx skipped: {tx_hash}")
            return

        # ── 3. Direction ──────────────────────────────────────────────────────

        direction = TxDirection.OUT if matched_address == from_addr else TxDirection.IN

        # ── 4. Parse block + raw ETH value ────────────────────────────────────

        try:
            raw_block = tx.get("blockNumber", "0x0") or "0x0"
            block_number = (
                int(raw_block, 16) if isinstance(raw_block, str) else int(raw_block)
            )
        except (ValueError, TypeError):
            block_number = 0

        try:
            raw_value = tx.get("value", "0x0") or "0x0"
            native_amount = int(raw_value, 16) / 1e18
        except (ValueError, TypeError):
            native_amount = 0.0

        # ── 5. Resolve token symbol + USD value via CoinGecko ─────────────────

        # Load wallet so we know the chain (ETH, POLYGON, BSC, etc.)
        wallet_obj = await db.get(TrackedWallet, wallet_id)
        chain = wallet_obj.chain.value if wallet_obj else "ethereum"

        # rawContract is populated by Alchemy for ERC-20 transfers
        raw_contract = tx.get("rawContract") or {}
        contract_address: str = (raw_contract.get("address") or "").lower()

        token_symbol = "ETH"
        amount = native_amount
        usd_value: float = 0.0

        if contract_address:
            # ── ERC-20 transfer ───────────────────────────────────────────────
            try:
                raw_hex = raw_contract.get("value") or "0x0"
                decimals = int(raw_contract.get("decimal") or "18", 0)
                token_amount = int(raw_hex, 16) / (10 ** decimals)
            except (ValueError, TypeError):
                token_amount = native_amount

            price, coingecko_id = await get_price_for_contract(contract_address, chain)
            usd_value = token_amount * price
            amount = token_amount

            # Derive a readable symbol from the resolved coingecko_id
            if contract_address in CONTRACT_TO_COINGECKO_ID:
                token_symbol = coingecko_id.split("-")[-1].upper()
            else:
                # Unknown contract — use first 6 chars of address as placeholder
                token_symbol = contract_address[:6].upper()

        else:
            # ── Native token (ETH / MATIC / BNB / SOL) ───────────────────────
            coingecko_id = NATIVE_TOKEN_IDS.get(chain, "ethereum")
            price = await get_price(coingecko_id)
            usd_value = native_amount * price
            token_symbol = coingecko_id.split("-")[-1].upper()

        # ── 6. Persist ────────────────────────────────────────────────────────

        tx_obj = Transaction(
            tx_hash=tx_hash,
            block_number=block_number,
            from_address=from_addr,
            to_address=to_addr,
            amount=amount,
            token_symbol=token_symbol,
            usd_value=usd_value,          # ✅ populated from CoinGecko
            direction=direction,
            wallet_id=wallet_id,
            timestamp=datetime.now(tz=timezone.utc),
            raw_data=tx,
        )

        db.add(tx_obj)
        await db.commit()
        await db.refresh(tx_obj)

        logger.info(
            f"Saved {tx_hash[:12]}… | {direction.value.upper()} | "
            f"{amount:.6f} {token_symbol} (~${usd_value:,.2f}) | "
            f"chain={chain} | wallet={wallet_id}"
        )

        # ── 7. Trigger alert rules ────────────────────────────────────────────
        await run_alert_for_tx(tx_obj, db)