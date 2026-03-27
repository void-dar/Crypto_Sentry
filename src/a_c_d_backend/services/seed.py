"""
Run once after init_db() to populate subscription_plans.

Usage:
    python -m app.db.seed

Or call seed() from a startup script / Alembic data migration.
"""

import asyncio
import logging

from sqlmodel import select

from ..db.main import Session
from ..db.models import SubscriptionPlan, Tier

logger = logging.getLogger(__name__)

PLANS = [
    {
        "name": "Free",
        "price_usd": 0.00,
        "max_wallets": 1,
        "max_alerts": 2,
        "tier": Tier.FREE,
    },
    {
        "name": "Starter",
        "price_usd": 9.99,
        "max_wallets": 5,
        "max_alerts": 10,
        "tier": Tier.STARTER,
    },
    {
        "name": "Pro",
        "price_usd": 29.99,
        "max_wallets": 50,
        "max_alerts": 100,
        "tier": Tier.PRO,
    },
]


async def seed() -> None:
    async with Session() as db:
        for plan_data in PLANS:
            # Idempotent — skip if already exists
            result = await db.exec(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.tier == plan_data["tier"]
                )
            )
            if result.scalar_one_or_none():
                logger.info(f"Plan '{plan_data['name']}' already exists — skipping")
                continue

            plan = SubscriptionPlan(**plan_data)
            db.add(plan)
            logger.info(f"Seeded plan: {plan_data['name']} (${plan_data['price_usd']})")

        await db.commit()
        logger.info("Seed complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())