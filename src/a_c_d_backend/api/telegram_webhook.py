import logging

from fastapi import APIRouter, Request, Response
from telegram import Update

from ..telegram_bot.app import build_application
from ..config import settings

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

# Module-level — same Application instance reused across requests
_application = None


def get_application():
    global _application
    if _application is None:
        _application = build_application()
    return _application


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """
    Telegram sends every user interaction here as a POST.
    We parse the Update and feed it to python-telegram-bot's dispatcher.
    """
    application = get_application()

    data = await request.json()
    update = Update.de_json(data, application.bot)

    # Initialize the application if this is the first request
    if not application.running:
        await application.initialize()
        await application.start()

    await application.process_update(update)
    return Response(content="ok", status_code=200)


async def set_webhook() -> bool:
    """
    Registers our webhook URL with Telegram.
    Called once during app startup.
    """
    application = get_application()
    webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL}"

    try:
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info(f"Telegram webhook set: {webhook_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return False


async def delete_webhook() -> None:
    """Called on shutdown to deregister the webhook."""
    try:
        application = get_application()
        await application.bot.delete_webhook()
        await application.stop()
        await application.shutdown()
        logger.info("Telegram webhook deleted")
    except Exception as e:
        logger.warning(f"Error during webhook cleanup: {e}")