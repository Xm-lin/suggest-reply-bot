import json

import re

from urllib.parse import urlparse

from urllib.request import Request, urlopen

from urllib.error import (
    HTTPError,
    URLError
)


class APIClientError(Exception):

    def __init__(
        self,
        message,
        kind="api"
    ):

        super().__init__(message)

        self.kind = kind


def normalize_base_url(api_url):

    api_url = api_url.strip().rstrip("/")

    if not api_url:

        raise APIClientError(
            "API URL 不可為空。",
            "url"
        )

    parsed = urlparse(
        api_url
    )

    if parsed.scheme not in (
        "http",
        "https"
    ) or not parsed.netloc:

        raise APIClientError(
            "API URL 格式不正確，請確認是完整的 http:// 或 https:// 網址。",
            "url"
        )

    if api_url.endswith(
        "/chat/completions"
    ):

        return api_url[
            :-len("/chat/completions")
        ]

    if api_url.endswith(
        "/models"
    ):

        return api_url[
            :-len("/models")
        ]

    return api_url


def _request(
    api_url,
    api_key,
    path,
    method="GET",
    payload=None,
    timeout=20
):

    base = normalize_base_url(
        api_url
    )

    url = f"{base}/{path.lstrip('/')}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "suggest-reply-bot/2.0"
    }

    if api_key:

        headers["Authorization"] = (
            f"Bearer {api_key}"
        )

    data = None

    if payload is not None:

        headers["Content-Type"] = (
            "application/json"
        )

        data = json.dumps(
            payload
        ).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers=headers,
        method=method
    )

    try:

        with urlopen(
            request,
            timeout=timeout
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="replace"
            )

            try:

                return json.loads(
                    raw
                )

            except json.JSONDecodeError:

                raise APIClientError(
                    "API 回傳的資料格式不是 JSON。",
                    "response"
                )

    except HTTPError as e:

        if e.code in (
            401,
            403
        ):

            raise APIClientError(
                "API Key 無效或沒有使用這個 API 的權限。",
                "auth"
            )

        if e.code == 404:

            raise APIClientError(
                "API 路徑不存在，請確認 API URL 是否正確。",
                "url"
            )

        if e.code == 429:

            raise APIClientError(
                "API 使用量已達限制，請稍後再試。",
                "rate_limit"
            )

        if e.code >= 500:

            raise APIClientError(
                "API 服務目前無法使用，請稍後再試。",
                "server"
            )

        raise APIClientError(
            f"API 回傳錯誤（HTTP {e.code}）。",
            "api"
        )

    except URLError:

        raise APIClientError(
            "無法連線到 API，請確認 API URL 或服務狀態。",
            "connection"
        )

    except TimeoutError:

        raise APIClientError(
            "API 回應逾時，請稍後再試。",
            "timeout"
        )


def natural_sort_key(
    value
):

    value = str(
        value
    ).lower()

    parts = re.split(
        r"(\d+(?:\.\d+)?)",
        value
    )

    key = []

    for part in parts:

        if not part:

            continue

        if re.fullmatch(
            r"\d+(?:\.\d+)?",
            part
        ):

            try:

                key.append(
                    (
                        1,
                        float(part)
                    )
                )

            except ValueError:

                key.append(
                    (
                        0,
                        part
                    )
                )

        else:

            key.append(
                (
                    0,
                    part
                )
            )

    return key


def supports_text_generation(
    item
):

    if not isinstance(
        item,
        dict
    ):

        return True

    supported_actions = (
        item.get(
            "supportedActions"
        )
        or item.get(
            "supported_actions"
        )
    )

    if supported_actions is not None:

        if isinstance(
            supported_actions,
            list
        ):

            return (
                "generateContent"
                in supported_actions
            )

    return True


def get_model_id(
    item
):

    if isinstance(
        item,
        str
    ):

        return item

    if isinstance(
        item,
        dict
    ):

        return (
            item.get("id")
            or item.get("name")
        )

    return None


def list_models(
    api_url,
    api_key
):

    data = _request(
        api_url,
        api_key,
        "models"
    )

    if isinstance(
        data,
        dict
    ):

        raw_models = data.get(
            "data"
        )

        if raw_models is None:

            raw_models = data.get(
                "models",
                []
            )

    elif isinstance(
        data,
        list
    ):

        raw_models = data

    else:

        raise APIClientError(
            "模型列表格式無法辨識。",
            "response"
        )

    models = []

    for item in raw_models:

        model_id = get_model_id(
            item
        )

        if not model_id:

            continue

        if not supports_text_generation(
            item
        ):

            continue

        model_id = str(
            model_id
        ).strip()

        if not model_id:

            continue

        if model_id.startswith(
            "models/"
        ):

            model_id = model_id[
                len("models/"):
            ]

        models.append(
            model_id
        )

    models = list(
        set(
            models
        )
    )

    models.sort(
        key=natural_sort_key,
        reverse=True
    )

    if not models:

        raise APIClientError(
            "API 沒有提供可用的模型。",
            "models"
        )

    return models


def extract_message_content(
    message
):

    if isinstance(
        message,
        str
    ):

        return message

    if not isinstance(
        message,
        dict
    ):

        return None

    content = message.get(
        "content"
    )

    if isinstance(
        content,
        str
    ):

        return content

    if isinstance(
        content,
        list
    ):

        text_parts = []

        for part in content:

            if isinstance(
                part,
                str
            ):

                text_parts.append(
                    part
                )

            elif isinstance(
                part,
                dict
            ):

                text = part.get(
                    "text"
                )

                if isinstance(
                    text,
                    str
                ):

                    text_parts.append(
                        text
                    )

        result = "".join(
            text_parts
        )

        if result.strip():

            return result

    return None


def chat_completion(
    api_url,
    api_key,
    model,
    messages,
    json_mode=False
):

    if not model:

        raise APIClientError(
            "尚未選擇模型，請先設定模型。",
            "model"
        )

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7
    }

    # 只有需要 JSON 的功能才要求 JSON。
    #
    # 這樣一般 API 仍然可以正常使用，
    # 不會被強制要求 response_format。
    if json_mode:

        payload["response_format"] = {
            "type": "json_object"
        }

    data = _request(
        api_url,
        api_key,
        "chat/completions",
        method="POST",
        payload=payload,
        timeout=90
    )

    try:

        choices = data.get(
            "choices"
        )

        if not isinstance(
            choices,
            list
        ) or not choices:

            raise APIClientError(
                "模型沒有回傳有效的 choices。",
                "response"
            )

        message = choices[0].get(
            "message"
        )

        content = extract_message_content(
            message
        )

        if content is None:

            raise APIClientError(
                "模型回覆格式錯誤：找不到文字內容。",
                "response"
            )

        return content.strip()

    except APIClientError:

        raise

    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError
    ):

        raise APIClientError(
            "模型回覆格式錯誤。",
            "response"
        )