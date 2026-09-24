import json

import re

from api_client import (
    APIClientError,
    chat_completion
)


def parse_model_json(
    text
):

    if not isinstance(
        text,
        str
    ):

        raise APIClientError(
            "模型沒有回傳文字內容。",
            "response"
        )

    text = text.strip()

    if not text:

        raise APIClientError(
            "模型沒有回傳內容。",
            "response"
        )

    # 先嘗試直接解析 JSON
    try:

        data = json.loads(
            text
        )

        if isinstance(
            data,
            dict
        ):

            return data

    except (
        json.JSONDecodeError,
        TypeError
    ):

        pass

    # 移除 Markdown code fence
    cleaned = re.sub(
        r"```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```",
        "",
        cleaned
    ).strip()

    # 再嘗試一次
    try:

        data = json.loads(
            cleaned
        )

        if isinstance(
            data,
            dict
        ):

            return data

    except (
        json.JSONDecodeError,
        TypeError
    ):

        pass

    # 如果前面還有其他文字，
    # 從第一個 { 開始解析 JSON object。
    start = cleaned.find(
        "{"
    )

    if start != -1:

        decoder = json.JSONDecoder()

        try:

            data, _ = decoder.raw_decode(
                cleaned[start:]
            )

            if isinstance(
                data,
                dict
            ):

                return data

        except (
            json.JSONDecodeError,
            TypeError
        ):

            pass

    raise APIClientError(
        "模型回覆格式錯誤，無法解析為 JSON。",
        "response"
    )


def analyze_and_generate(
    api_url,
    api_key,
    model,
    conversation_text,
    latest_message,
    has_user_history
):

    if has_user_history:

        style_instruction = """
請在內部分析「我」平常的聊天方式，包括：

- 常用詞
- 句子長度
- 口語程度
- 標點習慣
- 回覆長短
- 語氣直接或客氣
- 接續話題的方式
- 整體聊天節奏

這些分析不要輸出。

產生回答時，自然地接近我的平常聊天方式。
不要刻意模仿到不自然。
"""

    else:

        style_instruction = """
目前沒有足夠的我的歷史訊息。

請使用自然、簡短、口語化的繁體中文。

不要假裝知道我的說話習慣。
"""

    prompt = f"""
你是 Discord 聊天回覆助手。

請根據聊天紀錄完成兩件事情：

第一：

判斷「對方目前的狀態」。

例如：

- 分享近況
- 提問
- 抱怨
- 開玩笑
- 尋求幫助
- 延續話題
- 單純陳述事情
- 打招呼

第二：

根據對方狀態與聊天內容，
產生三種自然的回覆。

{style_instruction}

聊天紀錄：

{conversation_text}

對方最新訊息：

{latest_message}

回覆規則：

- 使用繁體中文
- 不要使用 Markdown
- 不要使用 emoji
- 不要過度熱情
- 不要突然變得正式
- 不要編造聊天紀錄沒有提到的事情
- 如果對方只是分享，不要假設對方需要幫助
- 三個回答要有明顯差異
- 回覆可以短，不需要硬湊長度
- 直接可以貼到 Discord
- 不要輸出分析過程

請只輸出 JSON。
JSON 必須符合以下結構：

{
    "status": "一句簡短的對方狀態描述",
    "replies": [
        {
            "style": "自然",
            "text": "..."
        },
        {
            "style": "關心",
            "text": "..."
        },
        {
            "style": "延續話題",
            "text": "..."
        }
    ]
}
"""

    text = chat_completion(
        api_url,
        api_key,
        model,
        [
            {
                "role": "user",
                "content": prompt
            }
        ],
        json_mode=True
    )

    data = parse_model_json(
        text
    )

    status = str(
        data.get(
            "status",
            ""
        )
    ).strip()

    if not status:

        status = (
            "目前無法判斷對方的聊天狀態。"
        )

    replies = data.get(
        "replies",
        []
    )

    result = []

    if not isinstance(
        replies,
        list
    ):

        raise APIClientError(
            "模型回覆格式錯誤：replies 不是列表。",
            "response"
        )

    for item in replies[:3]:

        if not isinstance(
            item,
            dict
        ):

            continue

        style = str(
            item.get(
                "style",
                ""
            )
        ).strip()

        reply_text = str(
            item.get(
                "text",
                ""
            )
        ).strip()

        if style and reply_text:

            result.append({
                "style": style,
                "text": reply_text
            })

    if not result:

        raise APIClientError(
            "模型沒有產生有效的建議回答。",
            "response"
        )

    return status, result


def format_final_result(
    status,
    replies
):

    output = (
        f"\n"
        f"對方狀態：{status}\n\n"
        f"－－－－－－－－\n"
        f"建議回答：\n"
    )

    for reply in replies:

        output += (
            f"{reply['style']}："
            f"{reply['text']}\n"
        )

    return output.strip()