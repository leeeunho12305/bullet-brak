"""클라 → 서버 WS 메시지 및 REST 요청/응답 pydantic 모델.

PROTOCOL §1 / §2.1 그대로. 검증 실패 시 해당 메시지는 무시한다(연결은 유지).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.accounts import (  # noqa: F401  (기존 import 경로 유지 — 지우지 말 것)
    AccountResponse,
    AuthResultResponse,
    BuyItemRequest,
    BuyItemResponse,
    CreateAnonAccountRequest,
    CreateAnonAccountResponse,
    LoginRequest,
    RecoveryCodeResponse,
    RedeemCodeRequest,
    SetCredentialsRequest,
    SetCredentialsResponse,
    UpdateProfileRequest,
)
from app.schemas.common import Customization, PartOffset  # noqa: F401

Mode = Literal["pvp", "training"]

# --------------------------------------------------------------------------
# REST (PROTOCOL §1)
# --------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    #: "on" = DB 연결됨, "off" = DATABASE_URL 없음(인메모리 모드).
    #: 프런트가 이 값으로 계정 기능을 켤지 정한다. 어느 쪽이든 200 이다
    #: (Render healthCheckPath 가 DB 때문에 실패하면 안 된다).
    db: Literal["on", "off"] = "off"


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Mode = "pvp"
    max_players: int = Field(default=2, ge=1, le=8)
    #: 맵 id 또는 "random". 모르는 값이면 서버가 기본 맵으로 되돌린다.
    map_id: str = Field(default="classic", max_length=32)
    #: 경쟁전 방. 켜면 서버가 인원을 2명으로, 맵을 "random" 으로 강제하고
    #: 입장에 계정을 요구한다(여기 실린 max_players/map_id 는 그때 무시된다).
    ranked: bool = False


class CreateRoomResponse(BaseModel):
    code: str
    mode: str
    max_players: int
    map_id: str = "classic"
    #: 서버가 확정한 값. 요청이 거절됐을 수도 있으므로(예: 훈련장) 이 값을 믿어야 한다.
    ranked: bool = False


class RoomInfoResponse(BaseModel):
    code: str
    mode: str
    max_players: int
    player_count: int
    phase: str
    map_id: str = "classic"
    ranked: bool = False


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
    #: DB 가 켜져 있고 토큰이 유효하면 이 값은 무시되고 계정 잔액이 쓰인다.
    coins: int = 0
    #: 디바이스 토큰. 있으면 서버가 계정을 찾아 프로필/코인을 계정 쪽으로 덮어쓴다.
    #: 쿼리스트링이 아니라 본문으로 받는다 — 액세스 로그에 남으면 안 되는 값이다.
    token: str | None = Field(default=None, max_length=128)

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


class SetMapMsg(BaseModel):
    """방장의 맵 선택(PROTOCOL §2.1 set_map). 값은 맵 id 또는 "random"."""

    model_config = ConfigDict(extra="ignore")

    map_id: str = Field(default="classic", max_length=32)


class SetPlatformsMsg(BaseModel):
    """방장의 맵 에디터 저장(PROTOCOL §2.1 set_platforms).

    좌표/종류 검증은 game.blocks.normalize_all 이 맡는다(월드 밖·이상한 종류는 잘려 나간다).
    """

    model_config = ConfigDict(extra="ignore")

    platforms: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


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


class RematchMsg(BaseModel):
    """매치 종료 후 리매치 투표(PROTOCOL §2.1 rematch). accept=False 면 거절."""

    model_config = ConfigDict(extra="ignore")

    accept: bool = True


#: type 문자열 → 페이로드 모델. 값이 None 이면 페이로드가 없는 메시지.
PAYLOAD_MODELS: dict[str, type[BaseModel] | None] = {
    "join": JoinMsg,
    "input": InputMsg,
    "aim": AimMsg,
    "shoot": None,
    "strong_start": None,
    "strong_release": None,
    "pick_card": PickCardMsg,
    #: 훈련장 전용. 전투 중에 카드 목록을 직접 연다(서버가 mode/phase 로 걸러낸다).
    "open_cards": None,
    "chat": ChatMsg,
    "start_game": None,
    "restart": None,
    "rematch": RematchMsg,
    "avatar": AvatarMsg,
    "set_map": SetMapMsg,
    "set_platforms": SetPlatformsMsg,
    "reset_platforms": None,
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
