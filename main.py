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
        ON CONFLICT(user_id) DO UPDATE SET api_key=excluded.api_key
    """, (user_id, api_key))
    conn.commit()
    conn.close()

def get_api_key(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM user_keys WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# =========================================================
# Render Port Dummy Server (防部署休眠)
# =========================================================
def run_dummy_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler)
    print(f"🌐 Dummy server running on port {PORT}")
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# =========================================================
# Bot 類別定義 (關鍵：使用 setup_hook 確保 100% 同步指令)
# =========================================================
class SuggestReplyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_db()
        print("🔄 正在向 Discord API 同步斜線指令...")
        try:
            synced = await self.tree.sync()
            print(f"✅【同步成功】已全域同步 {len(synced)} 個 Discord 指令！")
        except Exception as e:
            print(f"❌ 同步 Discord 指令失敗：{e}")

bot = SuggestReplyBot()

# 設定允許在伺服器、Bot 私訊、個人私訊中觸發指令
allowed_contexts = app_commands.AppCommandContext(
    guild=True,
    dm_channel=True,
    private_channel=True
)

# 設定允許安裝至伺服器與個人帳號
allowed_installs = app_commands.AppInstallationType(
    guild=True,
    user=True
)

@bot.event
async def on_ready():
    print(f"🚀 機器人 {bot.user} 已登入並準備就緒！")

# =========================================================
# /set_key
# =========================================================
@bot.tree.command(name="set_key", description="設定並儲存你的 Gemini API Key")
@app_commands.allowed_contexts(allowed_contexts)
@app_commands.allowed_installs(allowed_installs)
@app_commands.describe(api_key="輸入你的 Google Gemini API Key")
async def set_key(interaction: discord.Interaction, api_key: str):
    api_key = api_key.strip()
    if not api_key:
        await interaction.response.send_message("❌ API Key 不能是空白。", ephemeral=True)
        return

    try:
        client = genai.Client(api_key=api_key)
        models = list(client.models.list())
        generate_models = [m.name for m in models if "generateContent" in getattr(m, "supported_actions", [])]

        if not generate_models:
            await interaction.response.send_message("❌ 這個 API Key 沒有可用的 Gemini 文字生成模型。", ephemeral=True)
            return

        save_api_key(interaction.user.id, api_key)
        await interaction.response.send_message("✅ API Key 已成功驗證並儲存！", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ API Key 驗證失敗：\n`{str(e)[:1500]}`", ephemeral=True)

# =========================================================
# /reply
# =========================================================
@bot.tree.command(name="reply", description="生成自然的接話建議")
@app_commands.allowed_contexts(allowed_contexts)
@app_commands.allowed_installs(allowed_installs)
@app_commands.describe(prompt="輸入對方說的話或話題")
async def reply(interaction: discord.Interaction, prompt: str):
    api_key = get_api_key(interaction.user.id)
    if not api_key:
        await interaction.response.send_message("❌ 請先使用 `/set_key` 設定你的 Gemini API Key！", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"對方說了這句話：『{prompt}』。請提供一份自然且流暢的回覆建議。"
        )
        await interaction.followup.send(f"💡 **建議回覆：**\n{response.text}", ephemeral=True)
    except Exception as e:
        print(f"❌ /reply Gemini 錯誤：{e}")
        await interaction.followup.send(f"⚠️ 發生錯誤：\n```text\n{str(e)[:1800]}\n```", ephemeral=True)

# =========================================================
# 右鍵選單：建議回覆
# =========================================================
@bot.tree.context_menu(name="建議回覆")
@app_commands.allowed_contexts(allowed_contexts)
@app_commands.allowed_installs(allowed_installs)
async def jarvis_reply_context(interaction: discord.Interaction, message: discord.Message):
    api_key = get_api_key(interaction.user.id)
    if not api_key:
        await interaction.response.send_message("❌ 請先使用 `/set_key` 設定你的 Gemini API Key！", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"對方說了這句話：『{message.content}』。請提供一份自然且流暢的回覆建議。"
        )
        await interaction.followup.send(f"💡 **建議回覆：**\n{response.text}", ephemeral=True)
    except Exception as e:
        print(f"❌ 右鍵選單 Gemini 錯誤：{e}")
        await interaction.followup.send(f"⚠️ 發生錯誤：\n```text\n{str(e)[:1800]}\n```", ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ 找不到 DISCORD_BOT_TOKEN 環境變數！")
    else:
        print("🚀 正在啟動 Discord Bot...")
        bot.run(DISCORD_TOKEN)
