from pydantic import BaseModel
from typing import Optional

class PriceOut(BaseModel):
    coingecko_id: str
    price_usd: float
    cached: bool = True


class BatchPriceRequest(BaseModel):
    ids: list[str]


class BatchPriceOut(BaseModel):
    prices: dict[str, float]


class TokenInfoOut(BaseModel):
    id: str
    symbol: str
    name: str
    price_usd: float
    market_cap_usd: float
    volume_24h_usd: float
    price_change_24h_pct: float
    ath_usd: float
    image: Optional[str]


class ContractPriceOut(BaseModel):
    contract_address: str
    coingecko_id: str
    price_usd: float

