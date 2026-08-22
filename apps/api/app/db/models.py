"""계정/신원 테이블.

지금 단계의 목표는 딱 하나다: **"이 코인이 누구 것인가"에 답할 수 있게 만드는 것.**
로그인 UI 없이 시작하므로 계정은 익명으로 자동 생성되고, 브라우저가 들고 있는
디바이스 토큰이 그 계정을 가리킨다. 소셜 로그인은 나중에 `Account` 에
provider 컬럼을 붙여 승격시키면 된다.

JSON 컬럼은 Postgres 에서 JSONB 로 내려간다. 테스트는 sqlite 로도 돌아야 해서
`with_variant` 를 썼다.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# 경쟁전 테이블(시즌/랭크/매치 기록)은 파일 길이 때문에 따로 뒀다. alembic env.py 가
# import 하는 모듈은 여기 하나뿐이라, 이 줄이 있어야 Base.metadata 에 등록된다.
from app.db.ranked_models import (  # noqa: F401  (metadata 등록용 — 지우지 말 것)
    Match,
    MatchParticipant,
    RankProfile,
    Season,
)

#: Postgres 면 JSONB, 그 외(sqlite 테스트)는 일반 JSON
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class Account(Base):
    """플레이어 신원. 익명으로 생성되고 나중에 로그인으로 승격될 수 있다."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid_hex)

    nickname: Mapped[str] = mapped_column(String(16), default="익명", nullable=False)
    #: 아바타 커스터마이즈. 스키마는 schemas.messages.Customization 과 같은 모양.
    customization: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, default=dict, nullable=False
    )

    #: 서버 권위 재화. 클라이언트가 보내는 값은 여기에 절대 반영하지 않는다.
    coins: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: 전적. 매치 종료 시점에만 갱신한다(틱 루프 아님).
    matches_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: 사용자가 직접 정한 로그인 아이디(소문자로 정규화). 안 만들었으면 NULL 이다 —
    #: 익명 계정이 기본이고 아이디/비밀번호는 나중에 얹는 선택지다.
    login_id: Mapped[str | None] = mapped_column(
        String(32), unique=True, nullable=True, default=None
    )
    #: bcrypt 해시. 평문은 물론이고 되돌릴 수 있는 어떤 형태로도 저장하지 않는다.
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)

    #: 계정 인계 코드의 sha256 해시. 다른 기기에서 이 코드를 입력하면 디바이스 토큰이
    #: 하나 더 발급된다(= 로그인). 토큰과 같은 이유로 **평문은 저장하지 않는다** —
    #: 그래서 한 번 발급한 코드는 다시 보여줄 수 없고, 잊었으면 재발급뿐이다.
    #: 계정당 하나이며, 재발급하면 이전 코드는 그 즉시 죽는다.
    recovery_code_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, default=None
    )
    recovery_code_issued_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tokens: Mapped[list[AuthToken]] = relationship(
        back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )
    items: Mapped[list[AccountItem]] = relationship(
        back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )


class AuthToken(Base):
    """디바이스 토큰. 평문은 저장하지 않고 sha256 해시만 둔다.

    한 계정에 여러 개가 붙을 수 있다(브라우저를 바꿔도 계정을 잇고 싶을 때).
    """

    __tablename__ = "auth_tokens"

    #: sha256 hexdigest (64자)
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    #: 어디서 발급됐는지 알아보기 위한 메모(User-Agent 앞부분). 인증에는 쓰지 않는다.
    label: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="tokens", lazy="joined")


class AccountItem(Base):
    """스킨/파츠 소유권. 키 포맷은 프런트의 레거시와 동일하다 ("eyes:3")."""

    __tablename__ = "account_items"

    account_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    item_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    #: 구매 당시 지불한 코인. 환불/감사용.
    paid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    acquired_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="items")


Index("ix_auth_tokens_account_id", AuthToken.account_id)
Index("ix_accounts_last_seen_at", Account.last_seen_at)
