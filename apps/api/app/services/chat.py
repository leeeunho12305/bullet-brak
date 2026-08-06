"""채팅 메시지 생성."""

from __future__ import annotations

import time
from typing import Any

from app.game.models import ChatMessage, Room

MAX_TEXT_LEN = 200
MAX_HISTORY = 20


def sanitize(text: str) -> str:
    """널 문자를 제거하고 길이를 자른다."""
    return (text or "").replace("\x00", "").strip()[:MAX_TEXT_LEN]


def make_message(sender: str, text: str) -> ChatMessage:
    return ChatMessage(sender=sender or "System", text=sanitize(text), time=int(time.time() * 1000))


def to_dict(message: ChatMessage) -> dict[str, Any]:
    return {"sender": message.sender, "text": message.text, "time": message.time}


def push(room: Room, sender: str, text: str) -> dict[str, Any] | None:
    """방 히스토리에 추가하고 브로드캐스트용 payload 를 만든다. 빈 문자열이면 None."""
    message = make_message(sender, text)
    if not message.text:
        return None
    room.messages.append(message)
    if len(room.messages) > MAX_HISTORY:
        del room.messages[: len(room.messages) - MAX_HISTORY]
    return {"type": "chat", "message": to_dict(message)}
