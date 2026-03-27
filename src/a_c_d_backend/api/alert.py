import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..auth.services.dependency import get_current_user
from ..db.main import get_session as get_db
from ..db.models import AlertRule, TrackedWallet, User
from ...models.alert_rule import AlertRuleCreate, AlertRuleOut, AlertRuleUpdate

router = APIRouter(prefix="/wallets/{wallet_id}/alerts", tags=["alerts"])
logger = logging.getLogger(__name__)


async def _assert_wallet_ownership(
    wallet_id: UUID, user: User, db: AsyncSession
) -> TrackedWallet:
    wallet = await db.get(TrackedWallet, wallet_id)
    if not wallet or wallet.user_id != user.id or not wallet.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )
    return wallet


@router.post("/", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    wallet_id: UUID,
    rule_in: AlertRuleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRuleOut:
    await _assert_wallet_ownership(wallet_id, user, db)

    rule = AlertRule(
        wallet_id=wallet_id,
        type=rule_in.type,
        threshold_amount=rule_in.threshold_amount,
        token_symbol=rule_in.token_symbol,
        webhook_url=rule_in.webhook_url,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/", response_model=list[AlertRuleOut])
async def list_alerts(
    wallet_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRuleOut]:
    await _assert_wallet_ownership(wallet_id, user, db)
    result = await db.execute(
        select(AlertRule).where(AlertRule.wallet_id == wallet_id)
    )
    return result.scalars().all()


@router.get("/{rule_id}", response_model=AlertRuleOut)
async def get_alert(
    wallet_id: UUID,
    rule_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRuleOut:
    await _assert_wallet_ownership(wallet_id, user, db)
    rule = await db.get(AlertRule, rule_id)
    if not rule or rule.wallet_id != wallet_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


@router.patch("/{rule_id}", response_model=AlertRuleOut)
async def update_alert(
    wallet_id: UUID,
    rule_id: UUID,
    update_in: AlertRuleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertRuleOut:
    await _assert_wallet_ownership(wallet_id, user, db)
    rule = await db.get(AlertRule, rule_id)
    if not rule or rule.wallet_id != wallet_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    for field, value in update_in.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    wallet_id: UUID,
    rule_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _assert_wallet_ownership(wallet_id, user, db)
    rule = await db.get(AlertRule, rule_id)
    if not rule or rule.wallet_id != wallet_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    await db.delete(rule)
    await db.commit()