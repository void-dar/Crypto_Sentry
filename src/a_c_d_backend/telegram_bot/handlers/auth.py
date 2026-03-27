import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..api_client import api
from ..keyboard import main_menu_keyboard
from ..states import AWAITING_EMAIL, AWAITING_PASSWORD

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point — shown to every user who opens the bot."""
    user = update.effective_user
    token = context.user_data.get("token")

    if token:
        me = await api.get_me(token)
        if me:
            await update.message.reply_text(
                f"👋 Welcome back, <b>{me['username']}</b>!\n"
                f"Tier: <b>{me['tier'].upper()}</b>\n\n"
                f"Use the menu below to manage your wallets and alerts.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

    await update.message.reply_text(
        "👋 Welcome to <b>Crypto Sentry</b>!\n\n"
        "Track wallets, get whale alerts, and monitor tokens — all in Telegram.\n\n"
        "Use /login to sign in or /register to create an account.",
        parse_mode="HTML",
    )


# ── Login conversation ─────────────────────────────────────────────────────────

async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📧 Enter your email address:",
        reply_markup=None,
    )
    return AWAITING_EMAIL


async def login_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["login_email"] = update.message.text.strip()
    await update.message.reply_text("🔑 Enter your password:")
    return AWAITING_PASSWORD


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = context.user_data.pop("login_email", "")
    password = update.message.text.strip()

    # Delete password message immediately for security
    await update.message.delete()

    result = await api.login(email, password)

    if not result or "access_token" not in result:
        await update.message.reply_text(
            "❌ Invalid credentials. Try again with /login."
        )
        return ConversationHandler.END

    # Store token + auto-link their Telegram chat_id
    context.user_data["token"] = result["access_token"]
    chat_id = str(update.effective_chat.id)
    await api.link_telegram(result["access_token"], chat_id)

    me = await api.get_me(result["access_token"])
    await update.message.reply_text(
        f"✅ Logged in as <b>{me['username']}</b>!\n"
        f"Tier: <b>{me['tier'].upper()}</b>\n\n"
        f"Your Telegram is now linked — you'll receive alerts here.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Register conversation ──────────────────────────────────────────────────────

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📝 Let's create your account.\n\nEnter your desired username:"
    )
    context.user_data["reg_step"] = "username"
    return AWAITING_EMAIL   # reuse state — first input collected here


async def register_collect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    step = context.user_data.get("reg_step", "username")
    text = update.message.text.strip()

    if step == "username":
        context.user_data["reg_username"] = text
        context.user_data["reg_step"] = "email"
        await update.message.reply_text("📧 Enter your email address:")
        return AWAITING_EMAIL

    elif step == "email":
        context.user_data["reg_email"] = text
        context.user_data["reg_step"] = "password"
        await update.message.reply_text("🔑 Choose a password (min 8 chars, 1 uppercase, 1 digit):")
        return AWAITING_PASSWORD

    return AWAITING_EMAIL


async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    await update.message.delete()

    username = context.user_data.pop("reg_username", "")
    email = context.user_data.pop("reg_email", "")
    context.user_data.pop("reg_step", None)

    result = await api.register(username, email, password)

    if not result or "error" in (result or {}):
        error_msg = (result or {}).get("error", "Registration failed")
        await update.message.reply_text(f"❌ {error_msg}\n\nTry /register again.")
        return ConversationHandler.END

    # Auto-login after registration
    login_result = await api.login(email, password)
    if login_result and "access_token" in login_result:
        context.user_data["token"] = login_result["access_token"]
        chat_id = str(update.effective_chat.id)
        await api.link_telegram(login_result["access_token"], chat_id)

    await update.message.reply_text(
        f"🎉 Account created! Welcome, <b>{username}</b>!\n\n"
        f"Your Telegram is linked — whale alerts will come here.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Logged out. Use /login to sign in again.",
        reply_markup=None,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ── Conversation handlers (exported to bot.py) ─────────────────────────────────

login_conv = ConversationHandler(
    entry_points=[CommandHandler("login", login_start)],
    states={
        AWAITING_EMAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)
        ],
        AWAITING_PASSWORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", cancel),   # ✅ /start exits the flow
        CommandHandler("help", cancel),
    ],
    name="login_conv",
    persistent=False,
)

register_conv = ConversationHandler(
    entry_points=[CommandHandler("register", register_start)],
    states={
        AWAITING_EMAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, register_collect)
        ],
        AWAITING_PASSWORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", cancel),   # ✅
        CommandHandler("help", cancel),
    ],
    name="register_conv",
    persistent=False,
)