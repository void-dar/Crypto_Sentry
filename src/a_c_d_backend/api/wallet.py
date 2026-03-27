import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ..auth.services.dependency import get_current_user
from ..cache import invalidate_wallet
from ..db.main import get_session as get_db
from ..db.models import TrackedWallet, User
from ...models.wallet import WalletCreate, WalletOut, WalletUpdate

router = APIRouter(prefix="/wallets", tags=["wallets"])
logger = logging.getLogger(__name__)

TIER_WALLET_LIMITS = {"free": 1, "starter": 5, "pro": 50}


@router.post("/", response_model=WalletOut, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    wallet_in: WalletCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    # Tier enforcement
    limit = TIER_WALLET_LIMITS.get(user.tier.value, 1)
    count_result = await db.execute(
        select(func.count()).where(
            TrackedWallet.user_id == user.id,
            TrackedWallet.is_active == True,  # noqa: E712
        )
    )
    if count_result.scalar_one() >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{user.tier.value.title()} tier allows max {limit} wallet(s). Upgrade to add more.",
        )

    # Duplicate check per user
    existing = await db.execute(
        select(TrackedWallet).where(
            TrackedWallet.address == wallet_in.address,
            TrackedWallet.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already tracking this wallet address",
        )

    wallet = TrackedWallet(
        user_id=user.id,
        address=wallet_in.address,
        chain=wallet_in.chain,
        label=wallet_in.label,
    )
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)
    logger.info(f"User {user.id} added wallet {wallet.address} [{wallet.chain}]")
    return wallet


@router.get("/", response_model=list[WalletOut])
async def list_wallets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WalletOut]:
    result = await db.execute(
        select(TrackedWallet).where(
            TrackedWallet.user_id == user.id,
            TrackedWallet.is_active == True,  # noqa: E712
        )
    )
    return result.scalars().all()


@router.get("/{wallet_id}", response_model=WalletOut)
async def get_wallet(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    wallet = await db.get(TrackedWallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return wallet


@router.patch("/{wallet_id}", response_model=WalletOut)
async def update_wallet(
    wallet_id: UUID,
    update_in: WalletUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletOut:
    wallet = await db.get(TrackedWallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

    for field, value in update_in.model_dump(exclude_unset=True).items():
        setattr(wallet, field, value)

    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    wallet = await db.get(TrackedWallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

    # Soft delete — preserves transaction history
    wallet.is_active = False
    db.add(wallet)
    await db.commit()

    # Evict from Redis so process_tx stops matching this address
    await invalidate_wallet(wallet.address)
    logger.info(f"User {user.id} deactivated wallet {wallet.address}")