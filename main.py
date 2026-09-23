import os
import sqlite3
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import discord
from discord import app_commands
from discord.ext import commands
from google import genai


# =========================
# 基本設定
# =========================

PORT = int(os.environ.get("PORT", 10000))
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DB_NAME = "user_keys.db"

# Gemini 模型
GEMINI_MODEL = "gemini-3.6-flash"


# =========================
# SQLite 資料庫
# =========================

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
        DO UPDATE SET api_key = excluded.api_key
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

    if row:
        return row[0]

    return None


# =========================
# Render Dummy Web Server
# =========================

def run_dummy_server():
    try:
        server = HTTPServer(
            ("0.0.0.0", PORT),
            SimpleHTTPRequestHandler
        )

        print(f"🌐 Dummy server running on port {PORT}")

        server.serve_forever()

    except Exception as e:
        print(f"❌ Dummy server 啟動失敗：{e}")


threading.Thread(
    target=run_dummy_server,
    daemon=True
).start()


# =========================
# Discord Bot
# =========================

class SuggestReplyBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        # 保留 Message Content Intent
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        # 初始化資料庫
        init_db()

        print("🔄 正在向 Discord API 同步斜線指令...")

        try:

            synced = await self.tree.sync()

            print(
                f"✅【同步成功】已全域同步 "
                f"{len(synced)} 個 Discord 指令！"
            )

        except Exception as e:

            print(
                f"❌ 同步 Discord 指令失敗：{e}"
            )


bot = SuggestReplyBot()


# =========================
# Bot Ready
# =========================

@bot.event
async def on_ready():

    print(
        f"🚀 機器人 {bot.user} "
        f"已登入並準備就緒！"
    )


# ============================================================
# /set_key
# ============================================================

@bot.tree.command(
    name="set_key",
    description="設定並儲存你的 Gemini API Key"
)
@app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True
)
@app_commands.allowed_installs(
    guilds=True,
    users=True
)
@app_commands.describe(
    api_key="輸入你的 Google Gemini API Key"
)
async def set_key(
    interaction: discord.Interaction,
    api_key: str
):

    api_key = api_key.strip()

    # -------------------------
    # 檢查是否為空
    # -------------------------

    if not api_key:

        await interaction.response.send_message(
            "❌ API Key 不能是空白。"
        )

        return

    # -------------------------
    # 驗證 API Key
    # -------------------------

    try:

        print(
            f"🔑 使用者 {interaction.user.id} "
            f"正在驗證 Gemini API Key..."
        )

        client = genai.Client(
            api_key=api_key
        )

        # 嘗試取得模型列表
        models = list(
            client.models.list()
        )

        generate_models = [
            m.name
            for m in models
            if "generateContent"
            in getattr(
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

        # -------------------------
        # 儲存 API Key
        # -------------------------

        save_api_key(
            interaction.user.id,
            api_key
        )

        print(
            f"✅ 使用者 {interaction.user.id} "
            f"API Key 驗證成功"
        )

        await interaction.response.send_message(
            "✅ API Key 已成功驗證並儲存！\n"
            "現在可以使用 `/reply` 或右鍵訊息 → Apps → 建議回覆。"
        )

    except Exception as e:

        print(
            f"❌ /set_key API Key 驗證錯誤：{e}"
        )

        await interaction.response.send_message(
            "❌ API Key 驗證失敗：\n"
            f"```text\n"
            f"{str(e)[:1500]}"
            f"\n```"
        )


# ============================================================
# /reply
# ============================================================

@bot.tree.command(
    name="reply",
    description="生成自然的接話建議"
)
@app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True
)
@app_commands.allowed_installs(
    guilds=True,
    users=True
)
@app_commands.describe(
    prompt="輸入對方說的話或話題"
)
async def reply(
    interaction: discord.Interaction,
    prompt: str
):

    # -------------------------
    # 取得使用者 API Key
    # -------------------------

    api_key = get_api_key(
        interaction.user.id
    )

    if not api_key:

        await interaction.response.send_message(
            "❌ 請先使用 `/set_key` 設定你的 Gemini API Key！"
        )

        return

    # -------------------------
    # Discord 回應延遲
    # -------------------------

    await interaction.response.defer()

    try:

        print(
            f"💬 使用者 {interaction.user.id} "
            f"正在使用 /reply"
        )

        client = genai.Client(
            api_key=api_key
        )

        response = client.models.generate_content(

            model=GEMINI_MODEL,

            contents=(
                "你是一個 Discord 接話建議助手。\n"
                "請根據對方說的話，提供自然、口語、"
                "不尷尬的回覆建議。\n\n"
                f"對方說了：『{prompt}』\n\n"
                "只需要提供適合直接傳出去的回覆，"
                "不要解釋你的分析過程。"
            )
        )

        # -------------------------
        # 檢查 Gemini 回應
        # -------------------------

        if not response.text:

            await interaction.followup.send(
                "⚠️ Gemini 沒有產生文字回覆。"
            )

            return

        # -------------------------
        # 發送結果
        # -------------------------

        await interaction.followup.send(
            f"💡 **建議回覆：**\n"
            f"{response.text}"
        )

    except Exception as e:

        print(
            f"❌ /reply Gemini 錯誤：{e}"
        )

        await interaction.followup.send(
            "⚠️ 發生錯誤：\n"
            f"```text\n"
            f"{str(e)[:1800]}"
            f"\n```"
        )


# ============================================================
# 右鍵訊息 → Apps → 建議回覆
# ============================================================

@bot.tree.context_menu(
    name="建議回覆"
)
@app_commands.allowed_contexts(
    guilds=True,
    dms=True,
    private_channels=True
)
@app_commands.allowed_installs(
    guilds=True,
    users=True
)
async def jarvis_reply_context(
    interaction: discord.Interaction,
    message: discord.Message
):

    # -------------------------
    # 取得使用者 API Key
    # -------------------------

    api_key = get_api_key(
        interaction.user.id
    )

    if not api_key:

        await interaction.response.send_message(
            "❌ 請先使用 `/set_key` 設定你的 Gemini API Key！"
        )

        return

    # -------------------------
    # Discord 回應延遲
    # -------------------------

    await interaction.response.defer()

    try:

        print(
            f"🖱️ 使用者 {interaction.user.id} "
            f"使用右鍵「建議回覆」"
        )

        # -------------------------
        # 取得訊息內容
        # -------------------------

        message_content = message.content.strip()

        if not message_content:

            await interaction.followup.send(
                "⚠️ 這則訊息沒有文字內容，"
                "目前無法產生回覆建議。"
            )

            return

        # -------------------------
        # Gemini
        # -------------------------

        client = genai.Client(
            api_key=api_key
        )

        response = client.models.generate_content(

            model=GEMINI_MODEL,

            contents=(
                "你是一個 Discord 接話建議助手。\n"
                "請根據對方說的話，提供自然、口語、"
                "不尷尬的回覆建議。\n\n"
                f"對方說了：『{message_content}』\n\n"
                "只需要提供適合直接傳出去的回覆，"
                "不要解釋你的分析過程。"
            )
        )

        # -------------------------
        # 檢查 Gemini 回應
        # -------------------------

        if not response.text:

            await interaction.followup.send(
                "⚠️ Gemini 沒有產生文字回覆。"
            )

            return

        # -------------------------
        # 發送結果
        # -------------------------

        await interaction.followup.send(
            f"💡 **建議回覆：**\n"
            f"{response.text}"
        )

    except Exception as e:

        print(
            f"❌ 右鍵選單 Gemini 錯誤：{e}"
        )

        await interaction.followup.send(
            "⚠️ 發生錯誤：\n"
            f"```text\n"
            f"{str(e)[:1800]}"
            f"\n```"
        )


# ============================================================
# 啟動 Bot
# ============================================================

if __name__ == "__main__":

    if not DISCORD_TOKEN:

        print(
            "❌ 找不到 DISCORD_BOT_TOKEN 環境變數！"
        )

    else:

        print(
            "🚀 正在啟動 Discord Bot..."
        )

        try:

            bot.run(
                DISCORD_TOKEN
            )

        except Exception as e:

            print(
                f"❌ Discord Bot 啟動失敗：{e}"
            )
