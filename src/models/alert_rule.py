from pydantic import BaseModel, field_validator, UUID4
from typing import Optional
from ..a_c_d_backend.db.models import AlertType


class AlertRuleCreate(BaseModel):
    type: AlertType
    name: str
    threshold_amount: Optional[float] = None
    token_symbol: Optional[str] = None
    webhook_url: Optional[str] = None

    @field_validator("threshold_amount")
    @classmethod
    def threshold_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("threshold_amount must be greater than 0")
        return v

    @field_validator("token_symbol")
    @classmethod
    def token_symbol_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else v

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("webhook_url must be a valid HTTP/HTTPS URL")
        return v


class AlertRuleOut(BaseModel):
    id: UUID4
    name: str
    wallet_id: UUID4
    type: AlertType
    threshold_amount: Optional[float]
    token_symbol: Optional[str]
    webhook_url: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True, "json_encoders": {UUID4: str}}


class AlertRuleUpdate(BaseModel):
    threshold_amount: Optional[float] = None
    name: Optional[str] = None
    token_symbol: Optional[str] = None
    webhook_url: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("threshold_amount")
    @classmethod
    def threshold_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("threshold_amount must be greater than 0")
        return v