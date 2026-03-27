from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime
from ..a_c_d_backend.db.models import TxDirection


class TransactionOut(BaseModel):
    id: UUID4
    wallet_id: UUID4
    tx_hash: str
    block_number: int
    from_address: str
    to_address: str
    amount: float
    token_symbol: str
    usd_value: Optional[float]
    direction: TxDirection
    timestamp: datetime

    model_config = {"from_attributes": True, "json_encoders": {datetime: lambda v: v.isoformat(), UUID4: str}}


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int