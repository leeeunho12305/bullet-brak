"""채팅 욕설 필터 + 메시지 생성. 레거시 BAD_WORDS 정규식을 이식했다."""

from __future__ import annotations

import re
import time
from typing import Any

from app.game.models import ChatMessage, Room

#: 레거시 server/index.js 의 BAD_WORDS 와 동일한 목록
BAD_WORDS = re.compile(
    "|".join(
        [
            "바보",
            "멍청이",
            "정치",
            "섹스",
            "성미",
            "노무",
            "문재",
            "윤석",
            "이재",
            "정당",
            "공산",
            "친일",
            "선정",
        ]
    ),
    re.IGNORECASE,
)

MAX_TEXT_LEN = 200
MAX_HISTORY = 20


def sanitize(text: str) -> str:
    """욕설/금지어를 `***` 로 마스킹하고 길이를 자른다."""
    cleaned = (text or "").replace("\x00", "").strip()[:MAX_TEXT_LEN]
    return BAD_WORDS.sub("***", cleaned)


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
