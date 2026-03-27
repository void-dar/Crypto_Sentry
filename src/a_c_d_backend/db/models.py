from sqlmodel import SQLModel, Field, Relationship, Index
from sqlalchemy import Column, ForeignKey, Enum as SAEnum, text
import sqlalchemy.dialects.postgresql as pg
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
from decimal import Decimal


# ── Enums ──────────────────────────────────────────────────────────────────────

class ChainType(str, Enum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BSC = "bsc"
    SOLANA = "solana"


class Tier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class TxDirection(str, Enum):
    IN = "in"
    OUT = "out"


class AlertType(str, Enum):
    LARGE_TX = "large_tx"
    TOKEN_TRANSFER = "token_transfer"
    WALLET_ACTIVITY = "wallet_activity"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


# ── User ───────────────────────────────────────────────────────────────────────

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )

    username: str = Field(
        sa_column=Column(pg.VARCHAR(50), unique=False, nullable=False, index=True)
    )
    email: str = Field(
        sa_column=Column(pg.VARCHAR(150), unique=True, nullable=False, index=True)
    )
    hashed_password: str = Field(
        sa_column=Column(pg.VARCHAR(255), nullable=False)
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(pg.BOOLEAN, nullable=False, server_default="true"),
    )
    tier: Tier = Field(
        default=Tier.FREE,
        sa_column=Column(SAEnum(Tier, name="tier_enum", create_type=False), default=Tier.FREE, nullable=False),
    )
    subscription_expires: Optional[datetime] = Field(
        default=None,
        # ✅ was: Column(datetime(timezone=True)) — datetime is not a SA type
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=True),
    )
    tg_chat_id: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.TEXT, nullable=True, index=True),
    )

    last_seen: Optional[datetime] = Field(
        default=None,
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=True),
    )

    created_at: datetime = Field(
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        )
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            onupdate=text("CURRENT_TIMESTAMP"),
            nullable=True,
        )
    )

    wallets: List["TrackedWallet"] = Relationship(back_populates="user")
    subscriptions: List["Subscription"] = Relationship(back_populates="user")
    payments: List["Payment"] = Relationship(back_populates="user")


# ── TrackedWallet ──────────────────────────────────────────────────────────────

class TrackedWallet(SQLModel, table=True):
    __tablename__ = "tracked_wallets"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    user_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    address: str = Field(
        sa_column=Column(pg.VARCHAR(255), nullable=False, index=True)
    )
    label: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.VARCHAR(100), nullable=True),
    )
    chain: ChainType = Field(
        sa_column=Column(SAEnum(ChainType, name="chain_enum", create_type=False), nullable=False)
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(pg.BOOLEAN, server_default="true"),
    )
    last_checked_block: Optional[int] = Field(
        default=None,
        sa_column=Column(pg.BIGINT, nullable=True),
    )
    last_tx_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.TEXT, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        )
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            onupdate=text("CURRENT_TIMESTAMP"),
            nullable=True,
        )
    )

    user: "User" = Relationship(back_populates="wallets")
    transactions: List["Transaction"] = Relationship(
        back_populates="wallet",
        sa_relationship_kwargs={"cascade": "all, delete"},
    )
    alerts: List["AlertRule"] = Relationship(back_populates="wallet")


# ── Transaction ────────────────────────────────────────────────────────────────

class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_wallet_block", "wallet_id", "block_number"),
        Index("ix_transactions_from_to", "from_address", "to_address"),
        {"schema": None},  # if you ever use schemas
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    wallet_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("tracked_wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    tx_hash: str = Field(
        sa_column=Column(pg.VARCHAR(255), unique=True, nullable=False, index=True)
    )
    block_number: int = Field(
        sa_column=Column(pg.BIGINT, nullable=False, index=True)
    )
    from_address: str = Field(
        sa_column=Column(pg.VARCHAR(255), nullable=False)
    )
    to_address: str = Field(
        sa_column=Column(pg.VARCHAR(255), nullable=False)
    )
    amount: Decimal = Field(
        sa_column=Column(pg.NUMERIC(30, 18), nullable=False)  # better precision for crypto
    )
    token_symbol: str = Field(
        sa_column=Column(pg.VARCHAR(50), nullable=False)
    )
    usd_value: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(pg.NUMERIC(20, 4), nullable=True),
    )
    direction: TxDirection = Field(
        sa_column=Column(SAEnum(TxDirection, name="tx_direction_enum", create_type=False), nullable=False)
    )
    timestamp: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False)
    )
    raw_data: Dict = Field(
        sa_column=Column(pg.JSONB, nullable=False)
    )

    wallet: "TrackedWallet" = Relationship(back_populates="transactions")


# ── AlertRule ──────────────────────────────────────────────────────────────────

class AlertRule(SQLModel, table=True):
    __tablename__ = "alert_rules"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )

    name: str = Field(
        sa_column=Column(pg.VARCHAR(150), unique=False, nullable=False, index=True)
    )

    wallet_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("tracked_wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    type: AlertType = Field(
        sa_column=Column(SAEnum(AlertType, name="alert_type_enum", create_type=False), nullable=False)
    )
    threshold_amount: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(pg.NUMERIC(30, 10), nullable=True),
    )
    token_symbol: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.VARCHAR(50), nullable=True),
    )
    webhook_url: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.VARCHAR(500), nullable=True),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(pg.BOOLEAN, server_default="true"),
    )

    wallet: "TrackedWallet" = Relationship(back_populates="alerts")


# ── AlertLog ───────────────────────────────────────────────────────────────────

class AlertLog(SQLModel, table=True):
    __tablename__ = "alert_logs"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    wallet_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("tracked_wallets.id"),
            nullable=False,
            index=True,
        )
    )
    transaction_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("transactions.id"),
            nullable=False,
        )
    )
    message: str = Field(
        sa_column=Column(pg.TEXT, nullable=False)
    )
    triggered_at: datetime = Field(
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        )
    )


# ── SubscriptionPlan ───────────────────────────────────────────────────────────

class SubscriptionPlan(SQLModel, table=True):
    __tablename__ = "subscription_plans"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    name: str = Field(
        sa_column=Column(pg.VARCHAR(50), nullable=False)
    )
    price_usd: Decimal = Field(
        sa_column=Column(pg.NUMERIC(10, 2), nullable=False)
    )
    max_wallets: int = Field(
        sa_column=Column(pg.INTEGER, nullable=False)
    )
    max_alerts: int = Field(
        default=5,
        sa_column=Column(pg.INTEGER, nullable=False, server_default="5"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(pg.BOOLEAN, server_default="true"),
    )

    subscriptions: List["Subscription"] = Relationship(back_populates="plan")

# ── Subscription ───────────────────────────────────────────────────────────────

class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    user_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    plan_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("subscription_plans.id"),
            nullable=False,
        )
    )
    provider: str = Field(
        sa_column=Column(pg.VARCHAR(20), nullable=False)  # "stripe" | "paystack"
    )
    provider_subscription_id: Optional[str] = Field(
        default=None,
        sa_column=Column(pg.VARCHAR(255), nullable=True, index=True),
    )
    start_date: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False)
    )
    end_date: datetime = Field(
        sa_column=Column(pg.TIMESTAMP(timezone=True), nullable=False)
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(pg.BOOLEAN, server_default="true"),
    )

    user: "User" = Relationship(back_populates="subscriptions")
    plan: "SubscriptionPlan" = Relationship(back_populates="subscriptions")


# ── Payment ────────────────────────────────────────────────────────────────────

class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(pg.UUID(as_uuid=True), primary_key=True),
    )
    user_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("users.id"),
            nullable=False,
            index=True,
        )
    )
    plan_id: UUID = Field(
        sa_column=Column(
            pg.UUID(as_uuid=True),
            ForeignKey("subscription_plans.id"),
            nullable=False,
        )
    )
    amount: Decimal = Field(
        sa_column=Column(pg.NUMERIC(10, 2), nullable=False)
    )
    currency: str = Field(
        sa_column=Column(pg.VARCHAR(20), nullable=False)
    )
    tx_hash: str = Field(
        sa_column=Column(pg.VARCHAR(255), unique=True, nullable=False)
    )
    status: PaymentStatus = Field(
        default=PaymentStatus.PENDING,
        sa_column=Column(SAEnum(PaymentStatus, name="payment_status_enum", create_type=False), default=PaymentStatus.PENDING, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(
            pg.TIMESTAMP(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        )
    )
    user: "User" = Relationship(back_populates="payments")