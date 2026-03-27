from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["👛 My Wallets", "🪙 My Coins"],
            ["🔔 My Alerts", "📊 Dashboard"],
            ["💳 Subscription", "⚙️ Settings"],
            ["❓ Help"],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def wallet_actions_keyboard(wallet_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔔 Add Alert", callback_data=f"add_alert:{wallet_id}"),
                InlineKeyboardButton("📋 View Txs", callback_data=f"view_txs:{wallet_id}"),
            ],
            [
                InlineKeyboardButton("🗑️ Remove", callback_data=f"remove_wallet:{wallet_id}"),
            ],
        ]
    )


def alert_type_keyboard(wallet_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🐳 Large TX", callback_data=f"alert_type:large_tx:{wallet_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🪙 Token Transfer", callback_data=f"alert_type:token_transfer:{wallet_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "📡 All Activity", callback_data=f"alert_type:wallet_activity:{wallet_id}"
                )
            ],
        ]
    )


def chain_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ethereum", callback_data="chain:ethereum"),
                InlineKeyboardButton("Polygon", callback_data="chain:polygon"),
            ],
            [
                InlineKeyboardButton("BSC", callback_data="chain:bsc"),
                InlineKeyboardButton("Solana", callback_data="chain:solana"),
            ],
        ]
    )


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Starter — $9.99/mo", callback_data="subscribe:starter")],
            [InlineKeyboardButton("💎 Pro — $29.99/mo", callback_data="subscribe:pro")],
            [InlineKeyboardButton("❌ Cancel", callback_data="subscribe:cancel")],
        ]
    )


def confirm_keyboard(action: str, target_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"confirm:{action}:{target_id}"),
                InlineKeyboardButton("❌ No", callback_data="confirm:cancel"),
            ]
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back", callback_data="back:main")]]
    )