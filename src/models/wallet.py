from pydantic import BaseModel, field_validator, UUID4
from typing import Optional
from datetime import datetime
from ..a_c_d_backend.db.models import ChainType


class WalletCreate(BaseModel):
    address: str
    chain: ChainType
    label: Optional[str] = None

    @field_validator("address")
    @classmethod
    def normalise_address(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("address cannot be empty")
        return v.lower()

    @field_validator("label")
    @classmethod
    def clamp_label(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 100:
            raise ValueError("label must be 100 characters or fewer")
        return v.strip() if v else v


class WalletOut(BaseModel):
    id: UUID4
    user_id: UUID4
    address: str
    chain: ChainType
    label: Optional[str]
    is_active: bool
    last_tx_hash: Optional[str]
    last_checked_block: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {datetime: lambda v: v.isoformat(), UUID4: str}}


class WalletUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("label")
    @classmethod
    def clamp_label(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 100:
            raise ValueError("label must be 100 characters or fewer")
        return v.strip() if v else v