from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import os
import dotenv

dotenv.load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_NAME: str = os.getenv("DB_NAME", "")

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_URL: str = os.getenv("BASE_URL", "") + os.getenv("TELEGRAM_WEBHOOK_PATH")


    # Alchemy
    ALCHEMY_API_KEY: str = os.getenv("ALCHEMY_API_KEY", "")
    ALCHEMY_HTTP_URL: str = os.getenv("ALCHEMY_HTTP_URL", "")
    ALCHEMY_WEBHOOK_SECRET: str = os.getenv("ALCHEMY_WEBHOOK_SECRET", "")

    # CoinGecko
    COINGECKO_API_URL: str = os.getenv("COINGECKO_API_URL")
    COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY")

    # Payments
    PAYSTACK_SECRET_KEY: str = os.getenv("PAYSTACK_SECRET_KEY", "")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = os.getenv("REDIS_PORT", 6379)
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", "")

    # App
    APP_BASE_URL: str = os.getenv("APP_BASE_URL")
    BASE_URL: str = os.getenv("BASE_URL")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()