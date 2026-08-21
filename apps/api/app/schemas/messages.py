"""클라 → 서버 WS 메시지 및 REST 요청/응답 pydantic 모델.

PROTOCOL §1 / §2.1 그대로. 검증 실패 시 해당 메시지는 무시한다(연결은 유지).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.game import constants as C

Mode = Literal["pvp", "training"]

# --------------------------------------------------------------------------
# 공통
# --------------------------------------------------------------------------


class PartOffset(BaseModel):
    """파츠를 몸통 박스 대비 비율만큼 밀어 놓은 값(편집기의 드래그 결과)."""

    model_config = ConfigDict(extra="ignore")

    x: float = 0.0
    y: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def _clamp_axis(cls, v: float) -> float:
        f = float(v)
        if not math.isfinite(f):
            return 0.0
        return max(-C.MAX_PART_OFFSET, min(C.MAX_PART_OFFSET, f))


class Customization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eye: int = 0
    mouth: int = 0
    detail: int = 0
    detail2: int = 0
    color: str = "#ff6b6b"
    offsets: dict[str, PartOffset] = Field(default_factory=dict)

    @field_validator("eye", "mouth", "detail", "detail2")
    @classmethod
    def _clamp_index(cls, v: int) -> int:
        return max(0, min(C.MAX_PART_INDEX, int(v)))

    @field_validator("offsets")
    @classmethod
    def _known_slots(cls, v: dict[str, PartOffset]) -> dict[str, PartOffset]:
        return {k: off for k, off in v.items() if k in C.PART_SLOTS}

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
    #: "on" = DB 연결됨, "off" = DATABASE_URL 없음(인메모리 모드).
    #: 프런트가 이 값으로 계정 기능을 켤지 정한다. 어느 쪽이든 200 이다
    #: (Render healthCheckPath 가 DB 때문에 실패하면 안 된다).
    db: Literal["on", "off"] = "off"


# -- 계정 / 신원 -------------------------------------------------------------


class AccountResponse(BaseModel):
    """서버가 인정하는 나의 프로필. 코인·소유 아이템의 유일한 진실이다."""

    id: str
    nickname: str
    customization: Customization
    coins: int
    level: int
    xp: int
    matches_played: int
    matches_won: int
    owned_items: list[str] = Field(default_factory=list)
    #: 사용자가 직접 정한 로그인 아이디. 아직 안 만들었으면 None(= 이 기기에만 묶인 계정).
    login_id: str | None = None
    #: 인계 코드를 발급받아 둔 상태인가. **평문은 어떤 응답에도 다시 나오지 않는다.**
    has_recovery_code: bool = False


class CreateAnonAccountRequest(BaseModel):
    """익명 계정 발급. 기존 localStorage 프로필을 그대로 물려받기 위해 값을 받는다."""

    model_config = ConfigDict(extra="ignore")

    nickname: str = "익명"
    customization: Customization = Field(default_factory=Customization)
    #: localStorage 잔액 이관용. 서버가 ACCOUNT_SEED_COINS_MAX 로 자른다.
    seed_coins: int = 0
    #: 이미 갖고 있던 아이템 키("eyes:3"). 최초 1회만 그대로 인정한다.
    seed_items: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("nickname")
    @classmethod
    def _trim_nick(cls, v: str) -> str:
        v = (v or "").strip()
        return v[:16] if v else "익명"

    @field_validator("seed_coins")
    @classmethod
    def _clamp_seed(cls, v: int) -> int:
        return max(0, min(10_000_000, int(v)))


class CreateAnonAccountResponse(BaseModel):
    """평문 토큰은 여기서 딱 한 번만 나간다. 클라이언트가 잃으면 계정도 잃는다."""

    token: str
    account: AccountResponse


class RecoveryCodeResponse(BaseModel):
    """인계 코드 발급 결과.

    `code` 평문은 **이 응답에서만** 볼 수 있다. 서버는 해시만 갖고 있어서
    다시 보여줄 방법이 없고, 잊었으면 재발급(= 이전 코드 폐기)뿐이다.
    """

    code: str
    issued_at: dt.datetime


class RedeemCodeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    #: 하이픈/공백/대소문자는 서버가 알아서 정규화한다.
    code: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login_id: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AuthResultResponse(BaseModel):
    """로그인 / 인계 코드 사용의 결과.

    실패도 예외가 아니라 200 + ok=false 다(구매와 같은 관용구). 오타는 장애가 아니다.
    다만 시도 횟수 제한에 걸리면 429 로 끊는다 — 그건 정상 결과가 아니라 차단이다.

    실패 사유를 "아이디가 없음/비번이 틀림"으로 쪼개지 않는다. 쪼개는 순간
    그 창구가 **아이디 존재 여부를 알려주는 도구**가 된다.
    """

    ok: bool
    reason: Literal["ok", "invalid_code", "invalid_credentials"]
    #: 성공했을 때만 실린다. 이 기기의 새 디바이스 토큰이다.
    token: str | None = None
    account: AccountResponse | None = None


class SetCredentialsRequest(BaseModel):
    """아이디/비밀번호 설정(또는 변경). 로그인한 계정 위에 얹는다."""

    model_config = ConfigDict(extra="ignore")

    login_id: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class SetCredentialsResponse(BaseModel):
    ok: bool
    reason: Literal["ok", "taken", "invalid_id", "weak_password"]
    #: 성공했을 때 확정된 아이디(소문자로 정규화된 값).
    login_id: str | None = None
    #: 사용자에게 그대로 보여줄 안내. 규칙을 프런트에 두 벌 두지 않기 위해 서버가 문장을 준다.
    message: str = ""


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nickname: str | None = None
    customization: Customization | None = None

    @field_validator("nickname")
    @classmethod
    def _trim_nick(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return (v or "").strip()[:16] or "익명"


class BuyItemRequest(BaseModel):
    """구매(POST /api/me/items) 요청.

    **아이템 키 하나뿐이다.** 가격은 서버 가격표(`app.game.shop`)에서만 나오므로
    클라이언트가 price/coins 같은 걸 끼워 넣어도 `extra="ignore"` 로 통째로 버린다.
    """

    model_config = ConfigDict(extra="ignore")

    #: 레거시 포맷 그대로 "{category}:{index}" (예: "eyes:12").
    item_key: str = Field(min_length=1, max_length=48)


class BuyItemResponse(BaseModel):
    """구매 결과. 실패(코인 부족 등)도 예외가 아니라 200 + ok=false 로 돌아온다.

    coins/owned_items 는 **판정 직후의 서버 값**이다. 성공이든 실패든 이 값으로
    클라이언트 상태를 덮어쓰면 된다.
    """

    ok: bool
    reason: Literal["ok", "already_owned", "insufficient_coins", "invalid_item"]
    coins: int
    owned_items: list[str] = Field(default_factory=list)


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Mode = "pvp"
    max_players: int = Field(default=2, ge=1, le=8)
    #: 맵 id 또는 "random". 모르는 값이면 서버가 기본 맵으로 되돌린다.
    map_id: str = Field(default="classic", max_length=32)


class CreateRoomResponse(BaseModel):
    code: str
    mode: str
    max_players: int
    map_id: str = "classic"


class RoomInfoResponse(BaseModel):
    code: str
    mode: str
    max_players: int
    player_count: int
    phase: str
    map_id: str = "classic"


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
