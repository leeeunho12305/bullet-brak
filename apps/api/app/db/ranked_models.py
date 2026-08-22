"""경쟁전 테이블 — 시즌 / 랭크 프로필 / 매치 기록.

`models.py` 와 나눠 둔 이유는 길이뿐이다(파일당 400줄). alembic 이 metadata 를
집어갈 수 있도록 `models.py` 가 이 모듈을 한 번 import 한다 — 그 줄을 지우면
마이그레이션 자동 생성이 이 테이블들을 못 본다.

기록의 원칙 두 가지.

1. **매치 기록은 지우지 않는다.** 계정이 지워져도 매치 행은 남고 `account_id` 만
   NULL 이 된다(`ondelete="SET NULL"`). 상대의 전적에서 그 판이 통째로 사라지면
   기록이 아니라 착시가 된다.
2. **닉네임은 그 판 시점의 값을 복사해 둔다.** 나중에 닉네임을 바꿔도 예전 기록에는
   그때 이름이 남아야 한다.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.services import ranked


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class Season(Base):
    """경쟁전 시즌(발로란트의 '액트').

    활성 시즌은 항상 최대 하나다. 시즌이 바뀌면 랭크는 리셋되고 배치를 다시 보지만,
    지난 시즌의 `RankProfile` 행은 그대로 남아 "그때 무슨 티어였는지"를 증명한다.
    """

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: 사람이 읽는 식별자("act-1"). URL 과 로그에 쓴다.
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(48), nullable=False)

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    #: 지금 랭크가 걸리는 시즌인가. 한 번에 하나만 True 여야 한다.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RankProfile(Base):
    """계정 × 시즌의 랭크. `app.services.ranked.RankState` 가 이 행의 값 사본이다."""

    __tablename__ = "rank_profiles"

    account_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    season_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="CASCADE"), primary_key=True
    )

    #: 숨은 실력 점수(Elo). **어떤 응답에도 실리지 않는다** — 보이는 순간 사람들이
    #: 티어가 아니라 이 숫자를 보고 놀게 된다.
    mmr: Mapped[int] = mapped_column(Integer, default=ranked.BASE_MMR, nullable=False)
    #: 1~25. 0 이면 아직 배치 중이다.
    tier: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    placements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: 0 RR 에서 한 번 버틸 수 있는 강등 보호막.
    shield: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: 이 시즌에 찍은 최고점. 떨어져도 남는 값이라 프로필의 자랑거리가 된다.
    peak_tier: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    peak_rr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: 양수면 연승, 음수면 연패. 0 은 아직 한 판도 안 했다는 뜻이다.
    streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rounds_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rounds_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Match(Base):
    """끝난 매치 한 판. 일반전도 남긴다(랭크 변동만 경쟁전에 붙는다)."""

    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid_hex)
    #: 일반전은 시즌에 묶이지 않는다.
    season_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True, default=None
    )
    ranked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="pvp", nullable=False)
    #: 방 코드는 재사용되는 6자리라 식별자가 아니다. 문의 대응용 메모로만 둔다.
    room_code: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    map_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    #: 매치 전체 라운드 수와 걸린 시간.
    rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    winner_account_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, default=None
    )
    #: 상대가 도중에 나가서 끝난 판. 경쟁전에서는 이것도 승패로 친다
    #: (아니면 질 것 같을 때 나가는 게 최적 전략이 된다).
    forfeit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ended_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    participants: Mapped[list[MatchParticipant]] = relationship(
        back_populates="match", cascade="all, delete-orphan", lazy="selectin"
    )


class MatchParticipant(Base):
    """한 매치에서의 한 사람. 랭크 변동은 경쟁전일 때만 채워진다.

    PK 가 `(match_id, slot)` 인 이유는 **비로그인 참가자도 기록해야 하기 때문이다** —
    일반전에는 계정 없는 사람이 섞일 수 있어서 `account_id` 를 키로 쓸 수 없다.
    """

    __tablename__ = "match_participants"

    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    #: 방 안의 자리 번호(0, 1, …). 순서를 고정해 두면 기록을 다시 그릴 때 편하다.
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)

    account_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, default=None
    )
    #: 그 판 시점의 닉네임 사본. 나중에 바꿔도 옛 기록은 그대로여야 한다.
    nickname: Mapped[str] = mapped_column(String(16), default="", nullable=False)

    won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: 랭크 변동. 일반전이나 비로그인 참가자는 전부 0 이다.
    tier_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rr_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tier_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rr_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rr_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: 배치전 중이었으면 티어 대신 이 값이 의미를 갖는다.
    placement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    match: Mapped[Match] = relationship(back_populates="participants")


#: 리더보드 — 활성 시즌에서 티어·RR 내림차순. 이 순서가 곧 순위다.
Index(
    "ix_rank_profiles_leaderboard",
    RankProfile.season_id,
    RankProfile.tier.desc(),
    RankProfile.rr.desc(),
)
#: 내 전적 — 계정으로 참가 행을 찾고 매치로 조인한다.
Index("ix_match_participants_account_id", MatchParticipant.account_id)
Index("ix_matches_ended_at", Match.ended_at.desc())
Index("ix_matches_ranked_ended_at", Match.ranked, Match.ended_at.desc())
#: 활성 시즌은 하나뿐이라는 규칙을 인덱스로도 남겨 둔다(조회 경로이기도 하다).
UniqueConstraint(Season.key, name="uq_seasons_key")
Index("ix_seasons_is_active", Season.is_active)
