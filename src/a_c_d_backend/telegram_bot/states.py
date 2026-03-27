"""
Conversation state constants for ConversationHandler.
Each int is a unique state identifier.
"""

# Auth flow
AWAITING_EMAIL = 1
AWAITING_PASSWORD = 2

# Add wallet flow
AWAITING_WALLET_ADDRESS = 10
AWAITING_WALLET_CHAIN = 11
AWAITING_WALLET_LABEL = 12

# Add alert flow
AWAITING_ALERT_TYPE = 20
AWAITING_ALERT_NAME = 21
AWAITING_ALERT_THRESHOLD = 22
AWAITING_ALERT_TOKEN = 23

# Settings flow
AWAITING_TG_LINK_CONFIRM = 30