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

    parsed = urlparse(api_url)

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

    if api_url.endswith("/models"):

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

                return json.loads(raw)

            except json.JSONDecodeError:

                raise APIClientError(
                    "API 回傳的資料格式不是 JSON。",
                    "response"
                )

    except HTTPError as e:

        body = e.read().decode(
            "utf-8",
            errors="replace"
        )

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

    """
    判斷模型是否支援 generateContent。

    Gemini 官方的 Model API 會提供 supportedActions，
    Google 官方範例也是透過 generateContent 判斷。
    """

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

    # 有提供能力資訊時，
    # 只保留支援 generateContent 的模型。
    if supported_actions is not None:

        if isinstance(
            supported_actions,
            list
        ):

            return (
                "generateContent"
                in supported_actions
            )

    # 某些 OpenAI-compatible API
    # 不會提供 supportedActions。
    #
    # 這種情況不要全部排除，
    # 否則 OpenAI / OpenRouter / 其他相容 API
    # 可能會完全沒有模型可以選。
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

        # OpenAI-compatible API
        raw_models = data.get(
            "data"
        )

        # Gemini 原生 Models API
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

        # Gemini 原生 API 可能回傳：
        # models/gemini-xxx
        #
        # OpenAI-compatible API 通常回傳：
        # gemini-xxx
        #
        # 統一成模型 ID。
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


def chat_completion(
    api_url,
    api_key,
    model,
    messages
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

    data = _request(
        api_url,
        api_key,
        "chat/completions",
        method="POST",
        payload=payload,
        timeout=90
    )

    try:

        return data[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]

    except (
        KeyError,
        IndexError,
        TypeError
    ):

        raise APIClientError(
            "模型回傳格式無法辨識。",
            "response"
        )