import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .handlers.auth import (
    login_conv,
    logout,
    register_conv,
    start,
)
from .handlers.general import (
    dashboard,
    help_command,
    my_alerts,
    price_check,
    subscription_callback,
    subscription_menu,
    unknown_message,
)
from .handlers.wallets import (
    add_alert_conv,
    add_wallet_conv,
    list_wallets,
    remove_wallet_confirm,
    remove_wallet_execute,
    view_wallet_txs,
)
from ..config import settings

logger = logging.getLogger(__name__)


def build_application() -> Application:
    """
    Builds and returns the fully configured PTB Application.
    Called once at startup — the Application is stored on app.state.
    """
    application = (
        Application.builder()
        .token(settings.BOT_TOKEN)
        .build()
    )

    # ── Conversation handlers (must be first — highest priority) ──────────────
    application.add_handler(login_conv)
    application.add_handler(register_conv)
    application.add_handler(add_wallet_conv)
    application.add_handler(add_alert_conv)

    # ── Command handlers ───────────────────────────────────────────────────────
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("wallets", list_wallets))
    application.add_handler(CommandHandler("alerts", my_alerts))
    application.add_handler(CommandHandler("dashboard", dashboard))
    application.add_handler(CommandHandler("subscription", subscription_menu))
    application.add_handler(CommandHandler("price", price_check))
    application.add_handler(CommandHandler("help", help_command))

    # ── Inline button callbacks ────────────────────────────────────────────────
    application.add_handler(
        CallbackQueryHandler(remove_wallet_confirm, pattern="^remove_wallet:")
    )
    application.add_handler(
        CallbackQueryHandler(remove_wallet_execute, pattern="^confirm:")
    )
    application.add_handler(
        CallbackQueryHandler(view_wallet_txs, pattern="^view_txs:")
    )
    application.add_handler(
        CallbackQueryHandler(subscription_callback, pattern="^subscribe:")
    )

    # ── Text menu fallback ─────────────────────────────────────────────────────
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)
    )

    logger.info("Telegram bot application built")
    return application