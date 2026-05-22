import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from ..api_client import api
from ..keyboard import (
    alert_type_keyboard,
    back_keyboard,
    chain_keyboard,
    confirm_keyboard,
    main_menu_keyboard,
    wallet_actions_keyboard,
)
from ..states import (
    AWAITING_ALERT_NAME,
    AWAITING_ALERT_THRESHOLD,
    AWAITING_ALERT_TOKEN,
    AWAITING_ALERT_TYPE,
    AWAITING_WALLET_ADDRESS,
    AWAITING_WALLET_CHAIN,
    AWAITING_WALLET_LABEL,
)

logger = logging.getLogger(__name__)


def _require_auth(func):
    """Decorator — replies with login prompt if user has no token."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get("token"):
            msg = update.message or update.callback_query.message
            await msg.reply_text(
                "🔒 You need to log in first.\nUse /login to continue."
            )
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


# ── List wallets ───────────────────────────────────────────────────────────────

@_require_auth
async def list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    token = context.user_data["token"]
    wallets = await api.list_wallets(token)

    if not wallets:
        await update.message.reply_text(
            "You have no tracked wallets yet.\n\nUse /addwallet to add one.",
            reply_markup=main_menu_keyboard(),
        )
        return

    for w in wallets:
        label = w.get("label") or "Unlabelled"
        text = (
            f"👛 <b>{label}</b>\n"
            f"Chain: <code>{w['chain'].upper()}</code>\n"
            f"Address: <code>{w['address']}</code>\n"
            f"Last TX: <code>{w.get('last_tx_hash') or 'None'}</code>"
        )
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=wallet_actions_keyboard(w["id"]),
        )


# ── Add wallet conversation ────────────────────────────────────────────────────

@_require_auth
async def add_wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👛 <b>Add a wallet to track</b>\n\nEnter the wallet address:",
        parse_mode="HTML",
        reply_markup=None,
    )
    return AWAITING_WALLET_ADDRESS


async def add_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    address = update.message.text.strip()
    if len(address) < 10:
        await update.message.reply_text("❌ That doesn't look like a valid address. Try again:")
        return AWAITING_WALLET_ADDRESS

    context.user_data["new_wallet_address"] = address
    await update.message.reply_text(
        "⛓️ Select the chain:",
        reply_markup=chain_keyboard(),
    )
    return AWAITING_WALLET_CHAIN


async def add_wallet_chain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    chain = query.data.split(":")[1]
    context.user_data["new_wallet_chain"] = chain

    await query.message.reply_text(
        "🏷️ Enter a label for this wallet (or send /skip):"
    )
    return AWAITING_WALLET_LABEL


async def add_wallet_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    label: Optional[str] = None if text.startswith("/skip") else text

    token = context.user_data["token"]
    address = context.user_data.pop("new_wallet_address", "")
    chain = context.user_data.pop("new_wallet_chain", "ethereum")

    result = await api.add_wallet(token, address, chain, label)

    if not result or "error" in (result or {}):
        error = (result or {}).get("error", "Failed to add wallet")
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ <b>Wallet added!</b>\n"
        f"Address: <code>{result['address']}</code>\n"
        f"Chain: <code>{result['chain'].upper()}</code>\n"
        f"Label: {result.get('label') or '—'}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Remove wallet (via inline button) ─────────────────────────────────────────

async def remove_wallet_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    wallet_id = query.data.split(":")[1]
    context.user_data["pending_remove_wallet"] = wallet_id

    await query.message.reply_text(
        "⚠️ Are you sure you want to remove this wallet?\n"
        "All associated alerts will be deleted.",
        reply_markup=confirm_keyboard("remove_wallet", wallet_id),
    )


async def remove_wallet_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    action, wallet_id = parts[1], parts[2]

    if action == "cancel":
        await query.message.edit_text("❌ Cancelled.")
        return

    token = context.user_data.get("token")
    if not token:
        await query.message.edit_text("🔒 Session expired. Please /login again.")
        return

    success = await api.remove_wallet(token, wallet_id)
    if success:
        await query.message.edit_text("✅ Wallet removed.")
    else:
        await query.message.edit_text("❌ Failed to remove wallet. Try again.")


# ── View transactions inline ───────────────────────────────────────────────────

async def view_wallet_txs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    wallet_id = query.data.split(":")[1]
    token = context.user_data.get("token")

    if not token:
        await query.message.reply_text("🔒 Session expired. Please /login again.")
        return

    data = await api.get_transactions(token, wallet_id=wallet_id, page_size=5)
    if not data or not data.get("items"):
        await query.message.reply_text("No transactions found for this wallet.")
        return

    lines = [f"📋 <b>Last {len(data['items'])} transactions</b>\n"]
    for tx in data["items"]:
        direction = "📥" if tx["direction"] == "in" else "📤"
        usd = f"(~${tx['usd_value']:,.2f})" if tx.get("usd_value") else ""
        lines.append(
            f"{direction} <b>{tx['amount']:.4f} {tx['token_symbol']}</b> {usd}\n"
            f"   <code>{tx['tx_hash'][:20]}…</code>"
        )

    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


# ── Add alert from inline button ──────────────────────────────────────────────

async def add_alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    wallet_id = query.data.split(":")[1]
    context.user_data["alert_wallet_id"] = wallet_id

    await query.message.reply_text(
        "🔔 <b>Choose alert type:</b>",
        parse_mode="HTML",
        reply_markup=alert_type_keyboard(wallet_id),
    )
    return AWAITING_ALERT_TYPE



async def alert_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    alert_type = parts[1]
    wallet_id = parts[2]

    context.user_data["alert_type"] = alert_type
    context.user_data["alert_wallet_id"] = wallet_id

    # Ask for alert name first
    await query.message.reply_text(
        "📝 Enter a name for this alert (e.g., 'Big Whale TX', 'USDC Watch'):\n"
        "Or send /skip to use default naming.",
        parse_mode="HTML",
    )
    return AWAITING_ALERT_NAME

async def alert_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    alert_name = None if text.startswith("/skip") else escape_markdown(text)

    context.user_data["alert_name"] = alert_name

    # Proceed to threshold or token input based on alert type
    alert_type = context.user_data["alert_type"]
    query = update.message

    if alert_type == "large_tx":
        await query.reply_text(
            "💵 Enter the minimum USD threshold to trigger an alert\n"
            "e.g. <code>10000</code> for $10,000+",
            parse_mode="HTML",
        )
        return AWAITING_ALERT_THRESHOLD

    elif alert_type == "token_transfer":
        await query.reply_text(
            "🪙 Enter the token symbol to watch\ne.g. <code>USDC</code>",
            parse_mode="HTML",
        )
        return AWAITING_ALERT_TOKEN

    else:
        # wallet_activity — save immediately
        return await _save_alert(update, context, alert_type, context.user_data["alert_wallet_id"])


async def alert_threshold_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    try:
        threshold = float(update.message.text.strip().replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number (e.g. 10000):")
        return AWAITING_ALERT_THRESHOLD

    context.user_data["alert_threshold"] = threshold
    alert_type = context.user_data["alert_type"]
    wallet_id = context.user_data["alert_wallet_id"]
    return await _save_alert(update, context, alert_type, wallet_id, threshold=threshold)


async def alert_token_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    symbol = update.message.text.strip().upper()
    context.user_data["alert_token"] = symbol
    alert_type = context.user_data["alert_type"]
    wallet_id = context.user_data["alert_wallet_id"]
    return await _save_alert(
        update, context, alert_type, wallet_id, token_symbol=symbol
    )


async def _save_alert(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    alert_type: str,
    wallet_id: str,
    threshold: Optional[float] = None,
    token_symbol: Optional[str] = None,
) -> int:
    token = context.user_data.get("token")
    alert_name = context.user_data.get("alert_name")  # new
    msg = update.message or update.callback_query.message

    result = await api.add_alert(
        token, wallet_id, alert_type, threshold, token_symbol, name=alert_name
    )

    if not result or "error" in (result or {}):
        error = (result or {}).get("error", "Failed to create alert")
        await msg.reply_text(f"❌ {error}", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    type_labels = {
        "large_tx": "🐳 Large TX",
        "token_transfer": "🪙 Token Transfer",
        "wallet_activity": "📡 All Activity",
    }
    label = type_labels.get(alert_type, alert_type)
    extra = ""
    if threshold:
        extra = f"\nThreshold: <b>${threshold:,.0f}</b>"
    if token_symbol:
        extra = f"\nToken: <b>{token_symbol}</b>"

    alert_name_text = f"\nName: <b>{alert_name}</b>" if alert_name else ""

    await msg.reply_text(
        f"✅ <b>Alert created!</b>{alert_name_text}\n"
        f"Type: {label}{extra}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ── Exported conversation handlers ────────────────────────────────────────────

add_wallet_conv = ConversationHandler(
    entry_points=[
        CommandHandler("addwallet", add_wallet_start),
        MessageHandler(filters.Regex("^👛 My Wallets$"), list_wallets),
    ],
    states={
        AWAITING_WALLET_ADDRESS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_wallet_address)
        ],
        AWAITING_WALLET_CHAIN: [
            CallbackQueryHandler(add_wallet_chain, pattern="^chain:")
        ],
        AWAITING_WALLET_LABEL: [
            MessageHandler(filters.TEXT, add_wallet_label)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="add_wallet_conv",
)

add_alert_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(add_alert_start, pattern="^add_alert:"),
    ],
    states={
        AWAITING_ALERT_TYPE: [
            CallbackQueryHandler(alert_type_chosen, pattern="^alert_type:")
        ],
        AWAITING_ALERT_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, alert_name_received)
        ],
        AWAITING_ALERT_THRESHOLD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, alert_threshold_received)
        ],
        AWAITING_ALERT_TOKEN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, alert_token_received)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="add_alert_conv",
)