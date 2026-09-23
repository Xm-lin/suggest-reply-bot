import os

PORT = int(os.environ.get("PORT", 8080))
DB_FILE = "users.db"
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
