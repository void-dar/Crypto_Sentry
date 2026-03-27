import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..auth.services.dependency import get_current_user
from ..config import settings
from ..db.main import get_session as get_db
from ..db.models import Payment, Subscription, SubscriptionPlan, Tier, User, PaymentStatus
from ...models.subscriptions import (
    CheckoutResponse,
    PlanOut,
    SubscriptionOut,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ── Plans ──────────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)  # noqa: E712
    )
    return result.scalars().all()


@router.get("/me", response_model=SubscriptionOut | None)
async def my_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


# ── Stripe Checkout ────────────────────────────────────────────────────────────

@router.post("/stripe/checkout/{plan_id}", response_model=CheckoutResponse)
async def stripe_checkout(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user.email,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(plan.price_usd * 100),
                        "recurring": {"interval": "month"},
                        "product_data": {"name": plan.name},
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "user_id": str(user.id),
                "plan_id": str(plan.id),
            },
            success_url=f"{settings.APP_BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.APP_BASE_URL}/cancel",
        )
        return CheckoutResponse(checkout_url=session.url, provider="stripe")
    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Stripe error, try again")


# ── Paystack Checkout ──────────────────────────────────────────────────────────

@router.post("/paystack/checkout/{plan_id}", response_model=CheckoutResponse)
async def paystack_checkout(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Paystack amount is in kobo (NGN) or smallest currency unit
    amount_kobo = int(plan.price_usd * 100)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": user.email,
                    "amount": amount_kobo,
                    "metadata": {
                        "user_id": str(user.id),
                        "plan_id": str(plan.id),
                    },
                    "callback_url": f"{settings.APP_BASE_URL}/success",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return CheckoutResponse(
                checkout_url=data["data"]["authorization_url"],
                provider="paystack",
            )
    except httpx.HTTPError as e:
        logger.error(f"Paystack checkout error: {e}")
        raise HTTPException(status_code=500, detail="Paystack error, try again")


# ── Stripe Webhook ─────────────────────────────────────────────────────────────

@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = UUID(data["metadata"]["user_id"])
        plan_id = UUID(data["metadata"]["plan_id"])
        provider_sub_id = data.get("subscription")
        customer_id = data.get("customer")
        amount = data.get("amount_total", 0) / 100

        await _activate_subscription(
            db=db,
            user_id=user_id,
            plan_id=plan_id,
            provider="stripe",
            provider_customer_id=customer_id,
            provider_subscription_id=provider_sub_id,
            amount=amount,
            currency="usd",
            reference=data["id"],
        )

    elif event_type in (
        "customer.subscription.deleted",
        "customer.subscription.paused",
    ):
        provider_sub_id = data.get("id")
        await _cancel_subscription(db, provider_sub_id)

    elif event_type == "invoice.payment_failed":
        logger.warning(f"Stripe payment failed for customer: {data.get('customer')}")

    return {"status": "ok"}


# ── Paystack Webhook ───────────────────────────────────────────────────────────

@router.post("/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(None, alias="x-paystack-signature"),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(expected, x_paystack_signature or ""):
        logger.warning("Invalid Paystack webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event", "")
    data = payload.get("data", {})

    if event == "charge.success":
        metadata = data.get("metadata", {})
        user_id = UUID(metadata["user_id"])
        plan_id = UUID(metadata["plan_id"])
        amount = data.get("amount", 0) / 100
        currency = data.get("currency", "NGN").lower()
        reference = data.get("reference", "")

        await _activate_subscription(
            db=db,
            user_id=user_id,
            plan_id=plan_id,
            provider="paystack",
            provider_customer_id=data.get("customer", {}).get("customer_code"),
            provider_subscription_id=data.get("subscription_code"),
            amount=amount,
            currency=currency,
            reference=reference,
        )

    elif event in ("subscription.disable", "subscription.not_renew"):
        subscription_code = data.get("subscription_code")
        await _cancel_subscription(db, subscription_code)

    return {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _activate_subscription(
    db: AsyncSession,
    user_id: UUID,
    plan_id: UUID,
    provider: str,
    provider_customer_id: str | None,
    provider_subscription_id: str | None,
    amount: float,
    currency: str,
    reference: str,
) -> None:
    user = await db.get(User, user_id)
    plan = await db.get(SubscriptionPlan, plan_id)
    if not user or not plan:
        logger.error(
            f"_activate_subscription: user {user_id} or plan {plan_id} not found"
        )
        return

    now = datetime.now(tz=timezone.utc)
    end = now + timedelta(days=31)

    # Deactivate any existing subscription
    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.is_active == True,  # noqa: E712
        )
    )
    for old_sub in existing.scalars().all():
        old_sub.is_active = False
        db.add(old_sub)

    # Create new subscription record
    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        provider=provider,
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        start_date=now,
        end_date=end,
        is_active=True,
    )
    db.add(sub)

    # Log payment
    db.add(Payment(
        user_id=user_id,
        plan_id=plan_id,
        amount=amount,
        currency=currency,
        provider=provider,
        provider_reference=reference,
        status=PaymentStatus.COMPLETED,
    ))

    # Upgrade user tier
    user.tier = plan.tier
    user.subscription_expires = end
    db.add(user)

    await db.commit()
    logger.info(f"Activated {plan.tier} for user {user_id} via {provider}")


async def _cancel_subscription(db: AsyncSession, provider_sub_id: str | None) -> None:
    if not provider_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(
            Subscription.provider_subscription_id == provider_sub_id
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    sub.is_active = False
    db.add(sub)

    user = await db.get(User, sub.user_id)
    if user:
        user.tier = Tier.FREE
        user.subscription_expires = None
        db.add(user)

    await db.commit()
    logger.info(f"Cancelled subscription {provider_sub_id}")