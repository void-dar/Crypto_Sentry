import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..services.dependency import get_current_user
from ...db.main import get_session as get_db
from ...db.models import AlertLog, Payment, TrackedWallet, Transaction, User
from ..schemas import UserOut
from ....models.subscriptions import PaymentOut

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserOut)
async def get_profile(user: User = Depends(get_current_user)) -> UserOut:
    return user


@router.get("/me/payments", response_model=list[PaymentOut])
async def get_payment_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentOut]:
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
    )
    return result.scalars().all()


@router.get("/me/activity")
async def get_activity_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Returns a quick dashboard summary for the current user."""
    from sqlmodel import func

    # Wallet count
    wallet_count = await db.execute(
        select(func.count()).where(
            TrackedWallet.user_id == user.id,
            TrackedWallet.is_active == True,  # noqa: E712
        )
    )

    # Transaction count across all their wallets
    wallet_subq = (
        select(TrackedWallet.id)
        .where(TrackedWallet.user_id == user.id)
        .scalar_subquery()
    )
    tx_count = await db.execute(
        select(func.count()).where(Transaction.wallet_id.in_(wallet_subq))
    )

    # Alert log count (total alerts fired)
    alert_subq = (
        select(TrackedWallet.id)
        .where(TrackedWallet.user_id == user.id)
        .scalar_subquery()
    )
    alert_count = await db.execute(
        select(func.count()).where(AlertLog.wallet_id.in_(alert_subq))
    )

    return {
        "tier": user.tier.value,
        "wallets": wallet_count.scalar_one(),
        "transactions": tx_count.scalar_one(),
        "alerts_fired": alert_count.scalar_one(),
        "subscription_expires": user.subscription_expires,
    }