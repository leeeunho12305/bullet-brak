"""클라 → 서버 WS 메시지 및 REST 요청/응답 pydantic 모델.

PROTOCOL §1 / §2.1 그대로. 검증 실패 시 해당 메시지는 무시한다(연결은 유지).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Mode = Literal["pvp", "training"]

# --------------------------------------------------------------------------
# 공통
# --------------------------------------------------------------------------


class Customization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eye: int = 0
    mouth: int = 0
    detail: int = 0
    color: str = "#ff6b6b"

    @field_validator("eye", "mouth", "detail")
    @classmethod
    def _clamp_index(cls, v: int) -> int:
        return max(0, min(20, int(v)))

    @field_validator("color")
    @classmethod
    def _safe_color(cls, v: str) -> str:
        v = (v or "").strip()
        return v if v.startswith("#") and 4 <= len(v) <= 9 else "#ff6b6b"


# --------------------------------------------------------------------------
# REST (PROTOCOL §1)
# --------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Mode = "pvp"
    max_players: int = Field(default=2, ge=1, le=8)


class CreateRoomResponse(BaseModel):
    code: str
    mode: str
    max_players: int


class RoomInfoResponse(BaseModel):
    code: str
    mode: str
    max_players: int
    player_count: int
    phase: str


class CardInfoResponse(BaseModel):
    id: str
    name: str
    desc: str
    category: str
    color: str
    emoji: str


# --------------------------------------------------------------------------
# WebSocket 클라 → 서버 (PROTOCOL §2.1)
# --------------------------------------------------------------------------


class JoinMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nickname: str = "익명"
    customization: Customization = Field(default_factory=Customization)
    coins: int = 0

    @field_validator("nickname")
    @classmethod
    def _trim_nick(cls, v: str) -> str:
        v = (v or "").strip()
        return v[:16] if v else "익명"

    @field_validator("coins")
    @classmethod
    def _clamp_coins(cls, v: int) -> int:
        return max(0, min(10_000_000, int(v)))


class InputMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    left: bool = False
    right: bool = False
    jump: bool = False
    block: bool = False


class AimMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: float = 0.0
    y: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def _finite(cls, v: float) -> float:
        v = float(v)
        if v != v or v in (float("inf"), float("-inf")):  # NaN/Inf 차단
            return 0.0
        return max(-5000.0, min(5000.0, v))


class PickCardMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    card_id: str


class ChatMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str

    @field_validator("text")
    @classmethod
    def _trim_text(cls, v: str) -> str:
        return (v or "").strip()[:200]


class AvatarMsg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customization: Customization = Field(default_factory=Customization)


#: type 문자열 → 페이로드 모델. 값이 None 이면 페이로드가 없는 메시지.
PAYLOAD_MODELS: dict[str, type[BaseModel] | None] = {
    "join": JoinMsg,
    "input": InputMsg,
    "aim": AimMsg,
    "shoot": None,
    "strong_start": None,
    "strong_release": None,
    "pick_card": PickCardMsg,
    "chat": ChatMsg,
    "start_game": None,
    "restart": None,
    "avatar": AvatarMsg,
}


def parse_client_message(raw: dict[str, Any]) -> tuple[str, BaseModel | None] | None:
    """`{"type": ..., ...payload}` 를 (type, 검증된 모델|None) 로 변환. 실패 시 None."""
    if not isinstance(raw, dict):
        return None
    msg_type = raw.get("type")
    if not isinstance(msg_type, str) or msg_type not in PAYLOAD_MODELS:
        return None
    model = PAYLOAD_MODELS[msg_type]
    if model is None:
        return msg_type, None
    try:
        return msg_type, model.model_validate(raw)
    except Exception:
        return None
