import os
import sqlite3
import threading
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler

import discord
from discord import app_commands
from discord.ext import commands
from google import genai


# =========================================================
# 基本設定
# =========================================================

PORT = int(os.environ.get("PORT", 10000))
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

DB_NAME = "user_keys.db"


# =========================================================
# Gemini 模型庫
# 會按照這個順序嘗試
# =========================================================

GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.1-flash",
    "gemini-3-flash",
]


# =========================================================
# SQLite
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


def save_api_key(user_id, api_key):
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


def get_api_key(user_id):
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


# =========================================================
# Render Dummy Server
# =========================================================

class HealthHandler(SimpleHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def run_dummy_server():
    try:
        server = HTTPServer(
            ("0.0.0.0", PORT),
            HealthHandler
        )

        print(f"Dummy server running on port {PORT}")

        server.serve_forever()

    except Exception as e:
        print(f"Dummy server 啟動失敗：{e}")


threading.Thread(
    target=run_dummy_server,
    daemon=True
).start()


# =========================================================
# JSON 處理
# =========================================================

def parse_gemini_json(text):
    text = text.strip()

    # 移除 Markdown code fence
    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 找第一個 { 到最後一個 }
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    raise ValueError("Gemini 回傳的內容不是有效 JSON")


# =========================================================
# 判斷是否為暫時性 Gemini 錯誤
# =========================================================

def is_temporary_error(error):
    error_text = str(error).upper()

    temporary_keywords = [
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "500",
        "INTERNAL",
        "DEADLINE",
        "TIMEOUT",
        "408"
    ]

    return any(
        keyword in error_text
        for keyword in temporary_keywords
    )


# =========================================================
# Gemini 模型呼叫
# =========================================================

def generate_with_model_fallback(client, prompt):
    last_error = None

    for model in GEMINI_MODELS:

        try:
            print(f"正在使用 Gemini 模型：{model}")

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            print(f"Gemini 模型使用成功：{model}")

            return response.text

        except Exception as e:

            last_error = e

            print(
                f"Gemini 模型使用失敗：{model} -> {e}"
            )

            # 暫時性錯誤才換下一個模型
            if is_temporary_error(e):
                continue

            # 非暫時性錯誤直接停止
            raise e

    raise RuntimeError(
        f"所有 Gemini 模型都無法使用：{last_error}"
    )


# =========================================================
# 分析對方狀態
# =========================================================

def analyze_status(
    client,
    conversation_text
):

    prompt = f"""
你是一個 Discord 聊天分析助手。

請分析以下聊天內容中「對方目前的聊天狀態」。

只需要判斷：
1. 對方現在是在分享、提問、抱怨、開玩笑、尋求幫助、延續話題等哪一類狀態
2. 回覆時應該注意什麼

不要分析我的人格。
不要分析我的說話方式。
不要輸出你的分析過程。
不要提供建議回答。

請只輸出合法 JSON：

{{
    "status": "一句簡短的狀態描述"
}}

聊天內容：

{conversation_text}
"""

    text = generate_with_model_fallback(
        client,
        prompt
    )

    data = parse_gemini_json(text)

    status = str(
        data.get("status", "")
    ).strip()

    if not status:
        status = "目前無法判斷對方的聊天狀態。"

    return status


# =========================================================
# 產生回答
# =========================================================

def generate_replies(
    client,
    conversation_text,
    status,
    latest_message,
    has_user_history
):

    if has_user_history:

        style_instruction = """
請先在內部分析「我」平常的聊天方式，包括：

- 常用詞
- 句子長度
- 口語程度
- 標點習慣
- 回覆長短
- 語氣直接或客氣
- 如何接續話題
- 整體聊天節奏

不要把這些分析輸出。

最後產生的回答要自然地接近我的平常聊天方式。
不要刻意模仿到很奇怪。
"""

    else:

        style_instruction = """
目前沒有足夠的我的歷史訊息。

請使用自然、簡短、口語化的繁體中文。
不要假裝知道我的說話習慣。
"""

    prompt = f"""
你是一個 Discord 回覆建議助手。

以下是前面的聊天紀錄：

{conversation_text}

對方目前的狀態：

{status}

對方最新訊息：

{latest_message}

{style_instruction}

請產生三個不同方向的回覆：

1. 自然
最像一般聊天時自然接話。

2. 關心
比較有關心對方的感覺，但不要過度。

3. 延續話題
讓對話比較容易繼續下去。

重要規則：

- 只產生可以直接貼到 Discord 的文字。
- 不要使用 Markdown。
- 不要使用 emoji。
- 不要過度熱情。
- 不要突然變得很正式。
- 不要編造聊天紀錄沒有提到的背景。
- 如果對方只是分享事情，不要擅自假設對方需要幫忙。
- 三個回答必須有明顯差異。
- 回覆長度依照聊天情境決定，不要每個都寫很長。
- 不要輸出分析過程。
- 不要解釋為什麼這樣回答。

請只輸出合法 JSON：

{{
    "replies": [
        {{
            "style": "自然",
            "text": "..."
        }},
        {{
            "style": "關心",
            "text": "..."
        }},
        {{
            "style": "延續話題",
            "text": "..."
        }}
    ]
}}
"""

    text = generate_with_model_fallback(
        client,
        prompt
    )

    data = parse_gemini_json(text)

    replies = data.get("replies", [])

    result = []

    for item in replies[:3]:

        style = str(
            item.get("style", "")
        ).strip()

        reply_text = str(
            item.get("text", "")
        ).strip()

        if style and reply_text:
            result.append({
                "style": style,
                "text": reply_text
            })

    if not result:
        raise ValueError("Gemini 沒有產生有效的回答")

    return result


# =========================================================
# 取得對話紀錄
# =========================================================

async def get_conversation_for_user(
    channel,
    target_message,
    user_id,
    limit=15
):

    messages = []

    try:

        async for message in channel.history(
            before=target_message,
            limit=limit
        ):

            if not message.content.strip():
                continue

            if message.author.id == user_id:
                speaker = "我"

            elif message.author.id == target_message.author.id:
                speaker = "對方"

            else:
                speaker = "其他人"

            messages.append(
                f"{speaker}：{message.content}"
            )

    except Exception as e:

        print(
            f"取得聊天紀錄失敗：{e}"
        )

    messages.reverse()

    # 加入最新訊息
    messages.append(
        f"對方：{target_message.content}"
    )

    conversation_text = "\n".join(messages)

    user_reply_count = sum(
        1
        for message in messages
        if message.startswith("我：")
    )

    has_user_history = user_reply_count >= 2

    return conversation_text, has_user_history


# =========================================================
# 格式化最終回答
# =========================================================

def format_final_result(
    status,
    replies
):

    output = f"""對方狀態
{status}

建議回答
"""

    for reply in replies:

        output += (
            f"\n{reply['style']}\n"
            f"{reply['text']}\n"
        )

    return output.strip()


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

        await self.tree.sync()

        print("Slash commands synced")


bot = SuggestReplyBot()


# =========================================================
# Ready
# =========================================================

@bot.event
async def on_ready():

    print(
        f"Bot 已登入：{bot.user}"
    )


# =========================================================
# /set_key
# =========================================================

@bot.tree.command(
    name="set_key",
    description="設定你的 Gemini API Key"
)
@app_commands.describe(
    api_key="你的 Gemini API Key"
)
async def set_key(
    interaction: discord.Interaction,
    api_key: str
):

    try:

        client = genai.Client(
            api_key=api_key
        )

        # 驗證 API Key 是否可以看到模型
        models = list(
            client.models.list()
        )

        available_models = []

        for model in models:

            supported_actions = getattr(
                model,
                "supported_actions",
                []
            )

            if "generateContent" in supported_actions:

                name = getattr(
                    model,
                    "name",
                    ""
                )

                if name.startswith("models/"):
                    name = name[7:]

                available_models.append(name)

        if not available_models:

            await interaction.response.send_message(
                "這個 API Key 沒有可用的 Gemini 生成模型。",
                ephemeral=True
            )

            return

        save_api_key(
            interaction.user.id,
            api_key
        )

        await interaction.response.send_message(
            "Gemini API Key 設定成功。",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"API Key 驗證失敗：{e}"
        )

        await interaction.response.send_message(
            f"API Key 無法使用：{e}",
            ephemeral=True
        )


# =========================================================
# /reply
# =========================================================

@bot.tree.command(
    name="reply",
    description="分析訊息並產生建議回覆"
)
@app_commands.describe(
    message="對方傳給你的訊息"
)
async def reply_command(
    interaction: discord.Interaction,
    message: str
):

    api_key = get_api_key(
        interaction.user.id
    )

    if not api_key:

        await interaction.response.send_message(
            "你還沒有設定 Gemini API Key，請先使用 /set_key。",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        client = genai.Client(
            api_key=api_key
        )

        # =============================================
        # 1. 正在分析
        # =============================================

        await interaction.edit_original_response(
            content="""正在分析語氣...

對方狀態
分析中..."""
        )

        conversation_text = (
            f"對方：{message}"
        )

        status = analyze_status(
            client,
            conversation_text
        )

        # =============================================
        # 2. 分析完成
        # =============================================

        await interaction.edit_original_response(
            content=f"""對方狀態
{status}

正在產生回答..."""
        )

        # =============================================
        # 3. 產生回答
        # =============================================

        replies = generate_replies(
            client,
            conversation_text,
            status,
            message,
            False
        )

        # =============================================
        # 4. 最終結果
        # =============================================

        result = format_final_result(
            status,
            replies
        )

        await interaction.edit_original_response(
            content=result
        )

    except Exception as e:

        print(
            f"/reply 發生錯誤：{e}"
        )

        await interaction.edit_original_response(
            content=f"發生錯誤：{e}"
        )


# =========================================================
# 右鍵「建議回覆」
# =========================================================

@app_commands.context_menu(
    name="建議回覆"
)
async def suggest_reply(
    interaction: discord.Interaction,
    message: discord.Message
):

    api_key = get_api_key(
        interaction.user.id
    )

    if not api_key:

        await interaction.response.send_message(
            "你還沒有設定 Gemini API Key，請先使用 /set_key。",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        client = genai.Client(
            api_key=api_key
        )

        # =============================================
        # 1. 正在分析語氣
        # =============================================

        await interaction.edit_original_response(
            content="""正在分析語氣...

對方狀態
分析中..."""
        )

        # 取得前面的聊天紀錄
        conversation_text, has_user_history = (
            await get_conversation_for_user(
                interaction.channel,
                message,
                interaction.user.id
            )
        )

        # 分析對方狀態
        status = analyze_status(
            client,
            conversation_text
        )

        # =============================================
        # 2. 分析完成
        # =============================================

        await interaction.edit_original_response(
            content=f"""對方狀態
{status}

正在產生回答..."""
        )

        # =============================================
        # 3. 產生回答
        # =============================================

        replies = generate_replies(
            client,
            conversation_text,
            status,
            message.content,
            has_user_history
        )

        # =============================================
        # 4. 最終結果
        # =============================================

        result = format_final_result(
            status,
            replies
        )

        await interaction.edit_original_response(
            content=result
        )

    except Exception as e:

        print(
            f"建議回覆發生錯誤：{e}"
        )

        await interaction.edit_original_response(
            content=f"發生錯誤：{e}"
        )


# =========================================================
# 初始化資料庫
# =========================================================

init_db()


# =========================================================
# 啟動
# =========================================================

if not DISCORD_TOKEN:

    raise RuntimeError(
        "找不到 DISCORD_BOT_TOKEN"
    )


bot.run(DISCORD_TOKEN)
