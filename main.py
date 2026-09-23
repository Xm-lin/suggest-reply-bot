import os
import sqlite3
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import discord
from discord import app_commands
from discord.ext import commands
from google import genai


# =========================================================
# 環境變數與設定
# =========================================================
PORT = int(os.environ.get("PORT", 10000))
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DB_NAME = "user_keys.db"


# =========================================================
# SQLite 資料庫操作
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_api_key(user_id: int, api_key: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO user_keys (user_id, api_key)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET api_key=excluded.api_key
    """, (user_id, api_key))

    conn.commit()
    conn.close()


def get_api_key(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT api_key FROM user_keys WHERE user_id = ?",
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


# =========================================================
# Render Port Dummy Server
# =========================================================
def run_dummy_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        SimpleHTTPRequestHandler
    )

    print(f"🌐 Dummy server running on port {PORT}")
    server.serve_forever()


threading.Thread(
    target=run_dummy_server,
    daemon=True
).start()


# =========================================================
# Bot
# =========================================================
class SuggestReplyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        init_db()

        print("🔄 正在向 Discord API 同步指令...")

        try:
            synced = await self.tree.sync()

            print(
                f"✅【同步成功】已全域同步 "
                f"{len(synced)} 個 Discord 指令："
            )

            for command in synced:
                print(f"   • {command.name}")

        except Exception as e:
            print(f"❌ 同步 Discord 指令失敗：{e}")


bot = SuggestReplyBot()


# =========================================================
# /set_key
# 可使用於：
# - 伺服器
# - Bot 私訊
# - 群組私訊
#
# 可安裝於：
# - Guild Install
# - User Install
# =========================================================
@bot.tree.command(
    name="set_key",
    description="設定並儲存你的 Gemini API Key"
)
@app_commands.allowed_contexts(
    guild=True,
    dm_channel=True,
    private_channel=True
)
@app_commands.allowed_installs(
    guild=True,
    user=True
)
@app_commands.describe(
    api_key="輸入你的 Google Gemini API Key"
)
async def set_key(
    interaction: discord.Interaction,
    api_key: str
):
    api_key = api_key.strip()

    if not api_key:
        await interaction.response.send_message(
            "❌ API Key 不能是空白。"
        )
        return

    try:
        client = genai.Client(api_key=api_key)

        models = list(client.models.list())

        generate_models = [
            m.name
            for m in models
            if "generateContent" in getattr(
                m,
                "supported_actions",
                []
            )
        ]

        if not generate_models:
            await interaction.response.send_message(
                "❌ 這個 API Key 沒有可用的 Gemini 文字生成模型。"
            )
            return

        save_api_key(
            interaction.user.id,
            api_key
        )

        await interaction.response.send_message(
            "✅ API Key 已成功驗證並儲存！"
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ API Key 驗證失敗：\n"
            f"`{str(e)[:1500]}`"
        )


# =========================================================
# /reply
# =========================================================
@bot.tree.command(
    name="reply",
    description="生成自然的接話建議"
)
@app_commands.allowed_contexts(
    guild=True,
    dm_channel=True,
    private_channel=True
)
@app_commands.allowed_installs(
    guild=True,
    user=True
)
@app_commands.describe(
    prompt="輸入對方說的話或話題"
)
async def reply(
    interaction: discord.Interaction,
    prompt: str
):
    api_key = get_api_key(interaction.user.id)

    if not api_key:
        await interaction.response.send_message(
            "❌ 請先使用 `/set_key` 設定你的 Gemini API Key！"
        )
        return

    await interaction.response.defer()

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=(
                f"對方說了這句話：『{prompt}』。\n"
                "請提供一份自然、流暢、不尷尬的回覆建議。"
            )
        )

        await interaction.followup.send(
            f"💡 **建議回覆：**\n{response.text}"
        )

    except Exception as e:
        print(f"❌ /reply Gemini 錯誤：{e}")

        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            await interaction.followup.send(
                "⚠️ Gemini 目前負載較高，請稍後再試。"
            )
        else:
            await interaction.followup.send(
                f"⚠️ 發生錯誤：\n"
                f"```text\n{error_text[:1800]}\n```"
            )


# =========================================================
# 右鍵選單：建議回覆
#
# 可以：
# 對任何訊息按右鍵
# → Apps
# → 建議回覆
#
# 支援：
# - 伺服器
# - Bot DM
# - 私人聊天
# - User Install
# - Guild Install
# =========================================================
@bot.tree.context_menu(
    name="建議回覆"
)
@app_commands.allowed_contexts(
    guild=True,
    dm_channel=True,
    private_channel=True
)
@app_commands.allowed_installs(
    guild=True,
    user=True
)
async def jarvis_reply_context(
    interaction: discord.Interaction,
    message: discord.Message
):
    api_key = get_api_key(interaction.user.id)

    if not api_key:
        await interaction.response.send_message(
            "❌ 請先使用 `/set_key` 設定你的 Gemini API Key！"
        )
        return

    await interaction.response.defer()

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=(
                f"對方說了這句話：『{message.content}』。\n"
                "請提供一份自然、流暢、不尷尬的回覆建議。"
            )
        )

        await interaction.followup.send(
            f"💡 **建議回覆：**\n{response.text}"
        )

    except Exception as e:
        print(f"❌ 右鍵選單 Gemini 錯誤：{e}")

        error_text = str(e)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            await interaction.followup.send(
                "⚠️ Gemini 目前負載較高，請稍後再試。"
            )
        else:
            await interaction.followup.send(
                f"⚠️ 發生錯誤：\n"
                f"```text\n{error_text[:1800]}\n```"
            )


# =========================================================
# 啟動
# =========================================================
if __name__ == "__main__":

    if not DISCORD_TOKEN:
        print("❌ 找不到 DISCORD_BOT_TOKEN 環境變數！")

    else:
        print("🚀 正在啟動 Discord Bot...")
        bot.run(DISCORD_TOKEN)
