# Crypto Sentry

Async cryptocurrency tracking backend with real-time wallet monitoring,
automated billing, and Telegram bot notifications.

## The Problem

Crypto holders who track multiple wallets manually miss transactions,
can't set automated alerts, and have no unified view across chains.
Crypto Sentry automates wallet monitoring end-to-end — from on-chain
events to user notifications and subscription billing.

## What I Built

- **Webhook listener** — receives real-time transaction events from Alchemy
- **Wallet tracking system** — users register wallets, system monitors activity
- **Billing integration** — Paystack and Stripe subscription management
- **Telegram bot** — instant notifications when tracked wallets move
- **Async architecture** — non-blocking event processing throughout
- **Database migrations** — full Alembic migration history

## Key Technical Decisions

**Why async FastAPI over Django/Flask:** Transaction events arrive in
bursts. Async handling means the webhook endpoint never blocks while
processing previous events — critical for not missing rapid transactions.

**Why Alembic for migrations:** Crypto wallet data is financial data.
Schema changes need audit trails and rollback capability. Alembic gives
full migration history with up/down paths.

## Stack

- Python · FastAPI · PostgreSQL · Alembic · Poetry
- Alchemy Webhooks · Paystack · Stripe · Telegram Bot API

## Setup

```bash
git clone https://github.com/void-dar/Crypto_Sentry
cd Crypto_Sentry
poetry install
cp .env.example .env  # configure your keys
alembic upgrade head
uvicorn src.main:app --reload
```
