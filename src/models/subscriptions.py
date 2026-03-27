from pydantic import BaseModel, UUID4
from datetime import datetime
from ..a_c_d_backend.db.models import PaymentStatus
from ..a_c_d_backend.db.models import Tier


class PlanOut(BaseModel):
    id: UUID4
    name: str
    price_usd: float
    max_wallets: int
    max_alerts: int
    tier: Tier
    is_active: bool

    model_config = {"from_attributes": True, "json_encoders": {UUID4: str}}


class SubscriptionOut(BaseModel):
    id: UUID4
    plan_id: UUID4
    provider: str
    start_date: datetime
    end_date: datetime
    is_active: bool

    model_config = {"from_attributes": True, "json_encoders": {datetime: lambda v: v.isoformat(), UUID4: str}}


class CheckoutResponse(BaseModel):
    checkout_url: str
    provider: str


class PaymentOut(BaseModel):
    id: UUID4
    amount: float
    currency: str
    provider: str
    status: PaymentStatus
    created_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {datetime: lambda v: v.isoformat(), UUID4: str}}