import logging

from fastapi import APIRouter, Request, Response
from telegram import Update

from ..telegram_bot.app import build_application
from ..config import settings

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

_application = None


def get_application():
    global _application
    if _application is None:
        _application = build_application()
    return _application


async def setup_bot() -> None:
    """Called once in lifespan startup — initializes and registers webhook."""
    application = get_application()
    await application.initialize()
    await application.start()

    if settings.BOT_TOKEN and settings.TELEGRAM_WEBHOOK_URL:
        try:
            await application.bot.set_webhook(
                url=settings.TELEGRAM_WEBHOOK_URL,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            info = await application.bot.get_webhook_info()
            logger.info(f"Webhook set: {info.url}")
            if info.last_error_message:
                logger.warning(f"Webhook last error: {info.last_error_message}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.warning("BOT_TOKEN or TELEGRAM_WEBHOOK_URL missing — webhook skipped")


async def teardown_bot() -> None:
    """Called once in lifespan shutdown."""
    try:
        application = get_application()
        await application.bot.delete_webhook()
        await application.stop()
        await application.shutdown()
        logger.info("Bot shut down cleanly")
    except Exception as e:
        logger.warning(f"Bot shutdown error: {e}")


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """
    Telegram POSTs every user interaction here.
    We parse it and hand it to PTB's dispatcher.
    """
    application = get_application()

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)

    # Always return 200 — Telegram will retry on non-200 forever
    return Response(content="ok", status_code=200)