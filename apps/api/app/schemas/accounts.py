"""계정 / 신원 REST 스키마 (PROTOCOL §1.1).

`messages.py` 에서 떼어낸 조각이다(파일당 400줄). 호출부는 예전처럼
`app.schemas.messages` 에서 import 해도 된다 — 그쪽이 그대로 다시 내보낸다.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Customization

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
