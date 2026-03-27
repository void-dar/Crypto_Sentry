import logging
from telegram.helpers import escape
from telegram import Update
from telegram.ext import ContextTypes

from ..api_client import api
from ..keyboard import main_menu_keyboard, subscription_keyboard

logger = logging.getLogger(__name__)


def _require_token(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get("token"):
            await update.message.reply_text("🔒 Please /login first.")
            return
        return await func(update, context)
    return wrapper


@_require_token
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    token = context.user_data["token"]
    data = await api.get_activity(token)

    if not data:
        await update.message.reply_text("❌ Could not fetch dashboard. Try again.")
        return

    expires = data.get("subscription_expires")
    expires_str = expires[:10] if expires else "—"

    await update.message.reply_text(
        f"📊 <b>Your Dashboard</b>\n\n"
        f"Tier: <b>{data['tier'].upper()}</b>\n"
        f"Subscription expires: <b>{expires_str}</b>\n\n"
        f"👛 Wallets tracked: <b>{data['wallets']}</b>\n"
        f"📨 Transactions seen: <b>{data['transactions']}</b>\n"
        f"🔔 Alerts fired: <b>{data['alerts_fired']}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@_require_token
async def subscription_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    token = context.user_data["token"]
    sub = await api.get_subscription(token)
    plans = await api.get_plans()

    if sub and sub.get("is_active"):
        expires = (sub.get("end_date") or "")[:10]
        await update.message.reply_text(
            f"💳 <b>Your Subscription</b>\n\n"
            f"Plan: <b>{sub.get('provider', '').title()}</b>\n"
            f"Active until: <b>{expires}</b>\n\n"
            f"To upgrade, choose a plan below:",
            parse_mode="HTML",
            reply_markup=subscription_keyboard(),
        )
    else:
        plan_lines = "\n".join(
            f"• <b>{p['name']}</b> — ${p['price_usd']}/mo "
            f"({p['max_wallets']} wallets, {p['max_alerts']} alerts)"
            for p in plans
            if p["name"].lower() != "free"
        )
        await update.message.reply_text(
            f"💳 <b>Upgrade your plan</b>\n\n{plan_lines}\n\n"
            f"Choose a plan to get a checkout link:",
            parse_mode="HTML",
            reply_markup=subscription_keyboard(),
        )


async def subscription_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    action = query.data.split(":")[1]

    if action == "cancel":
        await query.message.edit_text("❌ Cancelled.")
        return

    token = context.user_data.get("token")
    if not token:
        await query.message.reply_text("🔒 Session expired. Please /login again.")
        return

    # Find the plan_id for the chosen tier
    plans = await api.get_plans()
    plan = next((p for p in plans if p["tier"] == action), None)

    if not plan:
        await query.message.reply_text("❌ Plan not found.")
        return

    # Default to Paystack for NGN users — you can make this configurable
    provider = "paystack"
    url = await api.get_checkout_url(token, plan["id"], provider)

    if not url:
        await query.message.reply_text("❌ Could not generate checkout link. Try again.")
        return

    await query.message.reply_text(
        f"💳 <b>Complete your payment</b>\n\n"
        f"Click the link below to subscribe to <b>{escape(plan['name'])}</b>:\n"
        f"{escape(url)}\n\n"
        f"_Your tier will be upgraded automatically after payment._",
        parse_mode="HTML",
    )


@_require_token
async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    token = context.user_data["token"]
    wallets = await api.list_wallets(token)

    if not wallets:
        await update.message.reply_text("You have no wallets yet. Add one first with /addwallet.")
        return

    found_any = False
    for wallet in wallets:
        alerts = await api.list_alerts(token, wallet["id"])
        if not alerts:
            continue

        found_any = True
        label = escape(wallet.get("label") or wallet["address"][:12] + "…")
        lines = [f"🔔 <b>Alerts for {label}</b>\n"]

        for a in alerts:
            status = "✅" if a["is_active"] else "⏸️"
            type_map = {
                "large_tx": "🐳 Large TX",
                "token_transfer": "🪙 Token Transfer",
                "wallet_activity": "📡 All Activity",
            }
            alert_label = type_map.get(a["type"], a["type"])
            extra = ""
            if a.get("threshold_amount"):
                extra = f" (≥${a['threshold_amount']:,.0f})"
            if a.get("token_symbol"):
                extra = f" ({a['token_symbol']})"

            lines.append(f"{status} {alert_label}{extra}")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
        )

    if not found_any:
        await update.message.reply_text(
            "No alerts configured yet.\n"
            "Go to 👛 My Wallets and tap 🔔 Add Alert on any wallet."
        )


@_require_token
async def price_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /price ethereum
    /price bitcoin
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /price <coingecko_id>\nExample: /price ethereum"
        )
        return

    coingecko_id = args[0].lower()
    token = context.user_data["token"]
    price = await api.get_price(token, coingecko_id)

    if price is None:
        await update.message.reply_text(
            f"❌ Could not find price for <code>{coingecko_id}</code>.\n"
            f"Make sure you're using the CoinGecko ID (e.g. <code>ethereum</code>, <code>usd-coin</code>).",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        f"💰 <b>{coingecko_id.upper()}</b> = <b>${price:,.4f}</b>",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Crypto Sentry — Commands</b>\n\n"
        "/start — Main menu\n"
        "/register — Create an account\n"
        "/login — Sign in\n"
        "/logout — Sign out\n\n"
        "<b>Wallets</b>\n"
        "/addwallet — Track a new wallet\n"
        "/wallets — List your wallets\n\n"
        "<b>Alerts</b>\n"
        "/alerts — View all your alerts\n\n"
        "<b>Prices</b>\n"
        "/price <id> — Check token price (e.g. /price ethereum)\n\n"
        "<b>Account</b>\n"
        "/dashboard — Your activity summary\n"
        "/subscription — Manage your plan\n"
        "/help — This message",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for menu button text that doesn't match a command."""
    text = (update.message.text or "").strip()

    routes = {
        "👛 My Wallets": "list_wallets",
        "🔔 My Alerts": "my_alerts",
        "📊 Dashboard": "dashboard",
        "💳 Subscription": "subscription_menu",
        "❓ Help": "help_command",
    }

    if text in routes:
        handlers = {
            "list_wallets": lambda: __import__(
                "app.bot.handlers.wallets", fromlist=["list_wallets"]
            ).list_wallets(update, context),
            "my_alerts": lambda: my_alerts(update, context),
            "dashboard": lambda: dashboard(update, context),
            "subscription_menu": lambda: subscription_menu(update, context),
            "help_command": lambda: help_command(update, context),
        }
        await handlers[routes[text]]()
    else:
        await update.message.reply_text(
            "I didn't understand that. Use /help to see available commands.",
            reply_markup=main_menu_keyboard(),
        )