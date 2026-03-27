import logging
from contextlib import asynccontextmanager
from sqlmodel import text
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from .services.seed import seed
from .cache import close as close_redis
from .config import settings
from .db.main import engine
from .api import wallet, alert, transaction, subscription, webhook, prices
from .auth.routes import auth, user
from .services.telegram import close as close_telegram
from .api.telegram_webhook import teardown_bot, router as telegram_router, setup_bot
from .telegram_bot.api_client import api as bot_api_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Crypto Sentry...")
    print("server is starting")
    await setup_bot()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            print("connection established")
            await seed()
    except Exception as e:
        print(f"Connection failed: {e}")
    yield
    logger.info("Shutting down...")
    print("Server shutting down....")
    await teardown_bot()
    await bot_api_client.close()
    await close_redis()
    await close_telegram()
    await engine.dispose()
    logger.info("Connections closed")


app = FastAPI(
    title="Crypto Sentry",
    description="Real-time wallet & whale tracking with Telegram alerts",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(wallet.router)
app.include_router(alert.router)
app.include_router(transaction.router)
app.include_router(subscription.router)
app.include_router(webhook.router)
app.include_router(prices.router)
app.include_router(telegram_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "env": settings.ENVIRONMENT}

