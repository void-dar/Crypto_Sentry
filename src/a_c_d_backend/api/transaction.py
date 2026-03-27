import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ..auth.services.dependency import get_current_user
from ..db.main import get_session as get_db
from ..db.models import TrackedWallet, Transaction, TxDirection, User
from ...models.transaction import TransactionOut, TransactionPage

router = APIRouter(prefix="/transactions", tags=["transactions"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=TransactionPage)
async def get_transactions(
    # ✅ Fixed: was Query(datetime.date) — not a valid default, raises TypeError
    date: Optional[date] = Query(None, description="Filter by date YYYY-MM-DD"),
    token_symbol: Optional[str] = Query(None, description="e.g. ETH, USDC"),
    direction: Optional[TxDirection] = Query(None),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    wallet_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionPage:
    # ✅ Fixed: was returning ALL transactions regardless of user
    # Scope to wallets owned by this user
    wallet_subq = (
        select(TrackedWallet.id)
        .where(
            TrackedWallet.user_id == user.id,
            TrackedWallet.is_active == True,  # noqa: E712
        )
        .scalar_subquery()
    )

    stmt = select(Transaction).where(Transaction.wallet_id.in_(wallet_subq))

    if date:
        stmt = stmt.where(func.date(Transaction.timestamp) == date)
    if token_symbol:
        stmt = stmt.where(Transaction.token_symbol == token_symbol.upper())
    if direction:
        stmt = stmt.where(Transaction.direction == direction)
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)
    if wallet_id:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)

    total_result = await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = total_result.scalar_one()

    stmt = (
        stmt.order_by(Transaction.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    return TransactionPage(
        items=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{tx_id}", response_model=TransactionOut)
async def get_transaction(
    tx_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionOut:
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Ownership check via wallet
    wallet = await db.get(TrackedWallet, tx.wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return tx