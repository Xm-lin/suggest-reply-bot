import os
import sqlite3
import threading
import json
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

        print(f"Dummy server running on port {PORT}")

        server.serve_forever()

    except Exception as e:
        print(f"Dummy server 啟動失敗：{e}")


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

        print("正在向 Discord API 同步斜線指令...")

        try:

            synced = await self.tree.sync()

            print(
                f"【同步成功】已全域同步 "
                f"{len(synced)} 個 Discord 指令！"
            )

        except Exception as e:

            print(
                f"同步 Discord 指令失敗：{e}"
            )


bot = SuggestReplyBot()


# =========================
# Bot Ready
# =========================

@bot.event
async def on_ready():

    print(
        f"機器人 {bot.user} "
        f"已登入並準備就緒！"
    )


# ============================================================
# Gemini JSON 解析
# ============================================================

def parse_gemini_json(text: str):
    """
    嘗試把 Gemini 回傳內容轉成 JSON。
    """

    text = text.strip()

    # 如果 Gemini 回傳 Markdown code block
    if text.startswith("```"):

        lines = text.splitlines()

        if len(lines) >= 3:

            lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

    try:

        return json.loads(text)

    except json.JSONDecodeError:

        # 嘗試找 JSON 物件
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1 and end > start:

            json_text = text[start:end + 1]

            return json.loads(json_text)

        raise


# ============================================================
# 整理 Gemini 結果
# ============================================================

def normalize_result(data):
    """
    確保 Gemini 回傳的資料符合程式需要的格式。
    """

    status = str(
        data.get(
            "status",
            "目前無法判斷對方的狀態。"
        )
    ).strip()

    replies = data.get(
        "replies",
        []
    )

    result = []

    if isinstance(replies, list):

        for item in replies:

            if not isinstance(item, dict):
                continue

            style = str(
                item.get(
                    "style",
                    "建議"
                )
            ).strip()

            text = str(
                item.get(
                    "text",
                    ""
                )
            ).strip()

            if text:

                result.append({
                    "style": style,
                    "text": text
                })

    # 如果 Gemini 沒有正常產生三個回答
    # 至少保留實際有產生的內容
    return status, result[:3]


# ============================================================
# 分析訊息
# ============================================================

def analyze_conversation(
    client,
    conversation_text: str,
    latest_message: str,
    has_user_history: bool
):
    """
    分析完整對話。

    conversation_text:
        前面的對話紀錄

    latest_message:
        最新訊息

    has_user_history:
        是否有足夠的使用者歷史回覆可供分析
    """

    if has_user_history:

        style_instruction = """
請先從「我的歷史回覆」中自行分析我的聊天習慣。

你要在內部分析：
- 常用詞
- 句子長度
- 口語程度
- 是否常用哈哈、喔、欸等口語詞
- 標點符號習慣
- 回覆通常簡短還是完整
- 回覆通常偏直接還是委婉
- 平常如何接話
- 整體聊天節奏

這些分析只能作為生成回答時的內部參考。

不要把「我的聊天習慣」或分析結果輸出給使用者。
不要說明你正在模仿使用者。
"""

    else:

        style_instruction = """
目前沒有足夠的「我的歷史回覆」可以分析。

請使用一般自然、口語、簡潔的繁體中文。
不要假裝知道使用者平常的聊天習慣。
"""

    prompt = f"""
你是一個 Discord 聊天回覆分析助手。

你的任務是：
1. 分析前面的對話。
2. 如果有我的歷史回覆，分析我的聊天風格。
3. 分析對方最新訊息的狀態、情緒與聊天意圖。
4. 產生三個不同方向的自然回覆。

{style_instruction}

========================
前面的對話
========================

{conversation_text}

========================
對方最新訊息
========================

{latest_message}

========================
輸出格式
========================

只能輸出合法 JSON：

{{
    "status": "簡短描述對方目前的狀態、情緒與聊天意圖",
    "replies": [
        {{
            "style": "自然",
            "text": "自然的直接回覆"
        }},
        {{
            "style": "關心",
            "text": "比較有關心感的回覆"
        }},
        {{
            "style": "延續話題",
            "text": "可以繼續聊天的回覆"
        }}
    ]
}}

========================
規則
========================

1. status 最多 2 句。
2. status 只描述對方，不要描述我的語氣。
3. 不要輸出你的分析過程。
4. 不要輸出我的聊天風格分析。
5. 三個回答必須有明顯不同。
6. 三個回答都要符合我的平常聊天風格。
7. 不要突然使用非常正式的文字。
8. 不要過度熱情。
9. 不要自行增加不存在的背景。
10. 不要使用 emoji。
11. 不要使用 Markdown。
12. 不要在回答外面加引號。
13. 回答要可以直接貼到 Discord 傳送。
14. 「自然」是最接近平常聊天的版本。
15. 「關心」是比較有情緒回應的版本。
16. 「延續話題」要盡量讓對話繼續。
17. 如果對方只是單純分享事情，也不要硬把它解讀成求助。
18. 必須輸出三個回答。
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    if not response.text:

        raise ValueError(
            "Gemini 沒有產生文字回應。"
        )

    data = parse_gemini_json(
        response.text
    )

    return normalize_result(data)


# ============================================================
# 格式化輸出
# ============================================================

def format_result(
    status: str,
    replies: list[dict]
):
    """
    產生最後顯示給使用者的文字。
    """

    lines = []

    lines.append("對方狀態")
    lines.append(status)
    lines.append("")
    lines.append("建議回答")
    lines.append("")

    for item in replies:

        style = item["style"]
        text = item["text"]

        lines.append(
            f"{style}："
        )

        lines.append(text)
        lines.append("")

    return "\n".join(lines).strip()


# ============================================================
# 取得前面的 Discord 對話
# ============================================================

async def get_conversation_history(
    message: discord.Message,
    limit: int = 15
):
    """
    取得指定訊息之前的最近幾則訊息。

    回傳：
        conversation_text
        has_user_history
    """

    messages = []

    try:

        async for msg in message.channel.history(
            limit=limit,
            before=message,
            oldest_first=False
        ):

            if not msg.content.strip():
                continue

            messages.append(msg)

    except Exception as e:

        print(
            f"讀取 Discord 歷史訊息失敗：{e}"
        )

        return (
            "沒有取得前面的對話紀錄。",
            False
        )

    # Discord history 是新的在前面
    # 這裡反過來變成舊 → 新
    messages.reverse()

    conversation_lines = []

    has_user_history = False

    for msg in messages:

        content = msg.content.strip()

        if not content:
            continue

        # 判斷是不是使用者自己
        if msg.author.id == message.author.id:

            # 注意：
            # 這裡不是用 interaction.user
            # 因為 message.author 才是這段聊天中
            # 真正需要分析的對象。
            #
            # 後面會重新依 interaction.user 判斷。
            speaker = "對方"

        else:

            speaker = "其他使用者"

        conversation_lines.append(
            f"{speaker}：{content}"
        )

    conversation_text = "\n".join(
        conversation_lines
    )

    if not conversation_text:

        conversation_text = (
            "沒有取得前面的文字訊息。"
        )

    return (
        conversation_text,
        has_user_history
    )


# ============================================================
# 取得前面的 Discord 對話
# ============================================================

async def get_conversation_for_user(
    message: discord.Message,
    user_id: int,
    limit: int = 15
):
    """
    取得最新訊息以前的對話。

    同時正確標示：
    - 我
    - 對方
    - 其他人

    並判斷是否有足夠的我的歷史回覆。
    """

    messages = []

    try:

        async for msg in message.channel.history(
            limit=limit,
            before=message,
            oldest_first=False
        ):

            if not msg.content.strip():
                continue

            messages.append(msg)

    except Exception as e:

        print(
            f"讀取歷史訊息失敗：{e}"
        )

        return (
            "沒有取得前面的對話紀錄。",
            False
        )

    messages.reverse()

    conversation_lines = []

    user_reply_count = 0

    for msg in messages:

        content = msg.content.strip()

        if not content:
            continue

        if msg.author.id == user_id:

            speaker = "我"
            user_reply_count += 1

        elif msg.author.id == message.author.id:

            speaker = "對方"

        else:

            speaker = "其他人"

        conversation_lines.append(
            f"{speaker}：{content}"
        )

    # 把最新訊息以前的內容作為上下文
    if conversation_lines:

        conversation_text = "\n".join(
            conversation_lines
        )

    else:

        conversation_text = (
            "沒有取得前面的文字訊息。"
        )

    # 至少有 2 則自己的歷史回覆，
    # 才認為足夠拿來判斷平常語氣。
    has_user_history = user_reply_count >= 2

    return (
        conversation_text,
        has_user_history
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
            "API Key 不能是空白。",
            ephemeral=True
        )

        return

    # -------------------------
    # 驗證 API Key
    # -------------------------

    try:

        print(
            f"使用者 {interaction.user.id} "
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
                "這個 API Key 沒有可用的 Gemini 文字生成模型。",
                ephemeral=True
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
            f"使用者 {interaction.user.id} "
            f"API Key 驗證成功"
        )

        await interaction.response.send_message(
            "API Key 已成功驗證並儲存！\n"
            "現在可以使用 `/reply` 或右鍵訊息 → Apps → 建議回覆。",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"/set_key API Key 驗證錯誤：{e}"
        )

        await interaction.response.send_message(
            "API Key 驗證失敗：\n"
            f"```text\n"
            f"{str(e)[:1500]}"
            f"\n```",
            ephemeral=True
        )


# ============================================================
# /reply
# ============================================================

@bot.tree.command(
    name="reply",
    description="分析訊息並提供三種回覆建議"
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
            "請先使用 `/set_key` 設定你的 Gemini API Key！",
            ephemeral=True
        )

        return

    # -------------------------
    # Discord 回應延遲
    # -------------------------

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        print(
            f"使用者 {interaction.user.id} "
            f"正在使用 /reply"
        )

        client = genai.Client(
            api_key=api_key
        )

        # /reply 沒有 Discord 歷史訊息，
        # 因此這裡只分析使用者輸入的內容。
        conversation_text = (
            "沒有提供前面的 Discord 對話紀錄。"
        )

        status, replies = analyze_conversation(
            client=client,
            conversation_text=conversation_text,
            latest_message=prompt,
            has_user_history=False
        )

        if not replies:

            await interaction.followup.send(
                "Gemini 沒有產生有效的回覆建議。",
                ephemeral=True
            )

            return

        result = format_result(
            status,
            replies
        )

        # 僅執行指令的使用者可見
        await interaction.followup.send(
            result,
            ephemeral=True
        )

    except json.JSONDecodeError:

        print(
            "/reply Gemini JSON 解析失敗"
        )

        await interaction.followup.send(
            "Gemini 回傳格式異常，請再試一次。",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"/reply Gemini 錯誤：{e}"
        )

        await interaction.followup.send(
            "發生錯誤：\n"
            f"```text\n"
            f"{str(e)[:1800]}"
            f"\n```",
            ephemeral=True
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
            "請先使用 `/set_key` 設定你的 Gemini API Key！",
            ephemeral=True
        )

        return

    # -------------------------
    # Discord 回應延遲
    # -------------------------

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        print(
            f"使用者 {interaction.user.id} "
            f"使用右鍵「建議回覆」"
        )

        # -------------------------
        # 取得最新訊息
        # -------------------------

        message_content = message.content.strip()

        if not message_content:

            await interaction.followup.send(
                "這則訊息沒有文字內容，"
                "目前無法產生回覆建議。",
                ephemeral=True
            )

            return

        # -------------------------
        # 取得前面對話
        # -------------------------

        conversation_text, has_user_history = (
            await get_conversation_for_user(
                message=message,
                user_id=interaction.user.id,
                limit=15
            )
        )

        print(
            f"取得前面對話完成，"
            f"是否有足夠使用者語氣資料："
            f"{has_user_history}"
        )

        # -------------------------
        # Gemini
        # -------------------------

        client = genai.Client(
            api_key=api_key
        )

        status, replies = analyze_conversation(
            client=client,
            conversation_text=conversation_text,
            latest_message=message_content,
            has_user_history=has_user_history
        )

        if not replies:

            await interaction.followup.send(
                "Gemini 沒有產生有效的回覆建議。",
                ephemeral=True
            )

            return

        # -------------------------
        # 發送結果
        # -------------------------

        result = format_result(
            status,
            replies
        )

        # 僅執行右鍵操作的使用者可見
        await interaction.followup.send(
            result,
            ephemeral=True
        )

    except json.JSONDecodeError:

        print(
            "右鍵選單 Gemini JSON 解析失敗"
        )

        await interaction.followup.send(
            "Gemini 回傳格式異常，請再試一次。",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.followup.send(
            "Bot 沒有權限讀取這個頻道的歷史訊息。",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"右鍵選單 Gemini 錯誤：{e}"
        )

        await interaction.followup.send(
            "發生錯誤：\n"
            f"```text\n"
            f"{str(e)[:1800]}"
            f"\n```",
            ephemeral=True
        )


# ============================================================
# 啟動 Bot
# ============================================================

if __name__ == "__main__":

    if not DISCORD_TOKEN:

        print(
            "找不到 DISCORD_BOT_TOKEN 環境變數！"
        )

    else:

        print(
            "正在啟動 Discord Bot..."
        )

        try:

            bot.run(
                DISCORD_TOKEN
            )

        except Exception as e:

            print(
                f"Discord Bot 啟動失敗：{e}"
            )
