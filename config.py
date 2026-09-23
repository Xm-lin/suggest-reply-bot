import os


PORT = int(os.environ.get("PORT", 10000))

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

DB_NAME = "user_keys.db"

MAX_MODELS_IN_SELECT = 25