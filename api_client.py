import json

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


def list_models(
    api_url,
    api_key
):

    data = _request(
        api_url,
        api_key,
        "models"
    )

    if isinstance(data, dict):

        raw_models = data.get(
            "data",
            []
        )

    elif isinstance(data, list):

        raw_models = data

    else:

        raise APIClientError(
            "模型列表格式無法辨識。",
            "response"
        )

    models = []

    for item in raw_models:

        if isinstance(item, str):

            model_id = item

        elif isinstance(item, dict):

            model_id = (
                item.get("id")
                or item.get("name")
            )

        else:

            model_id = None

        if model_id:

            models.append(
                str(model_id)
            )

    models = sorted(
        set(models),
        key=str.lower
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