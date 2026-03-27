import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from ..auth.services.dependency import get_current_user
from ..db.models import User
from ...models.prices import (
    PriceOut,
    BatchPriceRequest,
    BatchPriceOut,
    TokenInfoOut,
    ContractPriceOut,
)
from ..services.coingecko import (
    NATIVE_TOKEN_IDS,
    get_price,
    get_prices,
    get_price_for_contract,
    get_token_info,
)

router = APIRouter(prefix="/prices", tags=["prices"])
logger = logging.getLogger(__name__)



@router.get("/{coingecko_id}", response_model=PriceOut)
async def get_token_price(
    coingecko_id: str,
    _: User = Depends(get_current_user),
) -> PriceOut:
    """
    Get the current USD price for any CoinGecko token ID.
    e.g. GET /prices/ethereum  →  { coingecko_id: "ethereum", price_usd: 3200.50 }
    """
    price = await get_price(coingecko_id.lower())
    if price == 0.0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price not found for '{coingecko_id}'. Check the CoinGecko ID.",
        )
    return PriceOut(coingecko_id=coingecko_id, price_usd=price)


@router.post("/batch", response_model=BatchPriceOut)
async def get_batch_prices(
    body: BatchPriceRequest,
    _: User = Depends(get_current_user),
) -> BatchPriceOut:
    """
    Fetch prices for multiple CoinGecko IDs in one call.
    POST /prices/batch  body: { "ids": ["ethereum", "usd-coin", "tether"] }
    """
    if len(body.ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 IDs per batch request",
        )
    prices = await get_prices([i.lower() for i in body.ids])
    return BatchPriceOut(prices=prices)


@router.get("/contract/{contract_address}", response_model=ContractPriceOut)
async def get_contract_price(
    contract_address: str,
    chain: str = Query("ethereum", description="Chain: ethereum, polygon, bsc, solana"),
    _: User = Depends(get_current_user),
) -> ContractPriceOut:
    """
    Resolve a token contract address to a USD price.
    GET /prices/contract/0xa0b86991c...?chain=ethereum
    """
    price, coingecko_id = await get_price_for_contract(
        contract_address.lower(), chain.lower()
    )
    return ContractPriceOut(
        contract_address=contract_address.lower(),
        coingecko_id=coingecko_id,
        price_usd=price,
    )


@router.get("/info/{coingecko_id}", response_model=TokenInfoOut)
async def get_token_details(
    coingecko_id: str,
    _: User = Depends(get_current_user),
) -> TokenInfoOut:
    """
    Full token metadata — name, market cap, 24h volume, ATH, price change.
    GET /prices/info/ethereum
    """
    info = await get_token_info(coingecko_id.lower())
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token info not found for '{coingecko_id}'",
        )
    return TokenInfoOut(**info)


@router.get("/native/{chain}", response_model=PriceOut)
async def get_native_token_price(
    chain: str,
    _: User = Depends(get_current_user),
) -> PriceOut:
    """
    Get price of a chain's native token by chain name.
    GET /prices/native/ethereum  →  ETH price
    GET /prices/native/polygon   →  MATIC price
    GET /prices/native/bsc       →  BNB price
    """
    coingecko_id = NATIVE_TOKEN_IDS.get(chain.lower())
    if not coingecko_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown chain '{chain}'. Supported: {list(NATIVE_TOKEN_IDS.keys())}",
        )
    price = await get_price(coingecko_id)
    return PriceOut(coingecko_id=coingecko_id, price_usd=price)