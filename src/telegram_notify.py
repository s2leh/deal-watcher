from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class NotificationError(RuntimeError):
    pass


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise NotificationError("TELEGRAM_BOT_TOKEN is missing from .env.")
    if not TELEGRAM_CHAT_ID:
        raise NotificationError("TELEGRAM_CHAT_ID is missing from .env.")

    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urlencode(
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")

    request = Request(endpoint, data=payload, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise NotificationError(f"Failed to send the Telegram message: {exc}") from exc

    if not body.get("ok"):
        raise NotificationError(
            f"Telegram rejected the message: {body.get('description', 'unknown error')}"
        )
