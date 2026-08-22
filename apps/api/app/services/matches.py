"""매치 기록과 랭크 반영 — DB 를 만지는 쪽.

계산은 전부 `app.services.ranked`(순수 함수)가 하고, 여기서는 그 결과를 행에 옮기고
조회 쿼리를 제공한다.

⚠ **이 모듈의 함수는 60Hz 틱 루프에서 부르지 않는다.** 매치가 끝난 뒤 별도 태스크에서
한 번만 돈다(`app.services.results`). 틱 안에 `await db` 가 끼면 그 프레임이 밀린다.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account
from app.db.ranked_models import Match, MatchParticipant, RankProfile, Season
from app.services import accounts as account_service
from app.services import ranked
from app.services.seasons import active_season, list_seasons, start_next_season

logger = logging.getLogger(__name__)

#: 시즌 조회는 seasons 모듈이 담당한다. 호출부(라우터)가 여기 하나만 import 하면 되도록
#: 그대로 다시 내보낸다.
__all__ = [
    "MatchOutcome", "ParticipantResult", "active_season", "ensure_profile", "get_profile",
    "history", "leaderboard", "list_seasons", "position_of", "public_rank", "record",
    "start_next_season", "to_state",
]

#: 리더보드 한 번에 내려주는 최대 인원.
LEADERBOARD_LIMIT = 100
#: 전적 목록 기본/최대 개수.
HISTORY_DEFAULT = 20
HISTORY_MAX = 50


# --------------------------------------------------------------------------
# 틱 루프에서 넘어오는 값 사본
# --------------------------------------------------------------------------


@dataclass(slots=True)
class ParticipantResult:
    """매치가 끝난 순간의 참가자 한 명. Room/Player 객체를 들고 나오지 않는다 —
    방은 계속 바뀌므로 DB 태스크가 나중에 읽으면 이미 다른 상태다."""

    slot: int
    player_id: str
    account_id: str | None
    nickname: str
    score: int
    won: bool
    coins_earned: int = 0


@dataclass(slots=True)
class MatchOutcome:
    """끝난 매치 하나. `results.capture()` 가 만들어서 여기로 넘긴다."""

    room_code: str
    mode: str = "pvp"
    ranked: bool = False
    map_id: str = ""
    rounds: int = 0
    duration_sec: int = 0
    #: 상대가 도중에 나가서 끝난 판.
    forfeit: bool = False
    participants: list[ParticipantResult] = field(default_factory=list)

    def rank_eligible(self) -> bool:
        """랭크를 걸어도 되는 판인가.

        경쟁전 방이고, 정확히 두 명이며, 둘 다 계정에 묶여 있어야 한다. 방 입장에서
        이미 같은 조건을 검사하지만 여기서 한 번 더 본다 — 판정의 최종 책임은 기록하는
        쪽에 있어야 하고, 조건이 깨진 판은 조용히 일반전처럼 남는 편이 안전하다.
        """
        return (
            self.ranked
            and self.mode == "pvp"
            and len(self.participants) == 2
            and all(p.account_id for p in self.participants)
        )


# --------------------------------------------------------------------------
# 랭크 프로필
# --------------------------------------------------------------------------


def to_state(profile: RankProfile) -> ranked.RankState:
    return ranked.RankState(
        mmr=profile.mmr,
        tier=profile.tier,
        rr=profile.rr,
        placements=profile.placements,
        shield=profile.shield,
    )


async def get_profile(
    session: AsyncSession, account_id: str, season_id: int
) -> RankProfile | None:
    return await session.get(RankProfile, (account_id, season_id))


async def ensure_profile(
    session: AsyncSession, account_id: str, season: Season
) -> RankProfile:
    """이 시즌의 랭크 프로필. 없으면 만든다.

    직전 시즌 기록이 있으면 MMR 을 일부 물려받는다(`ranked.soft_reset`) — 시즌마다
    완전히 0에서 시작하면 잘하는 사람이 배치 내내 초보와 만나게 된다.
    """
    profile = await session.get(RankProfile, (account_id, season.id))
    if profile is not None:
        return profile

    previous = await session.scalar(
        select(RankProfile)
        .where(RankProfile.account_id == account_id, RankProfile.season_id != season.id)
        .order_by(RankProfile.season_id.desc())
        .limit(1)
    )
    seed = ranked.soft_reset(to_state(previous)) if previous is not None else ranked.RankState()

    profile = RankProfile(
        account_id=account_id,
        season_id=season.id,
        mmr=seed.mmr,
        tier=seed.tier,
        rr=seed.rr,
        placements=seed.placements,
        shield=seed.shield,
    )
    session.add(profile)
    await session.flush()
    return profile


def _apply_to_profile(
    profile: RankProfile, change: ranked.RankChange, *, score: int, opponent_score: int
) -> None:
    """계산 결과를 행에 옮긴다. 통계(연승·최고점)도 여기서 같이 갱신한다."""
    after = change.after
    profile.mmr = after.mmr
    profile.tier = after.tier
    profile.rr = after.rr
    profile.placements = after.placements
    profile.shield = after.shield

    if change.won:
        profile.wins += 1
        profile.streak = max(1, profile.streak + 1)
    else:
        profile.losses += 1
        profile.streak = min(-1, profile.streak - 1)
    profile.best_streak = max(profile.best_streak, profile.streak)

    profile.rounds_won += max(0, score)
    profile.rounds_lost += max(0, opponent_score)

    # 최고점은 떨어져도 남는다. 이 시즌의 자랑거리라서 내려 쓰지 않는다.
    if (after.tier, after.rr) > (profile.peak_tier, profile.peak_rr):
        profile.peak_tier, profile.peak_rr = after.tier, after.rr

    profile.updated_at = dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------------------
# 기록
# --------------------------------------------------------------------------


async def record(session: AsyncSession, outcome: MatchOutcome) -> dict[str, dict[str, Any]]:
    """매치를 저장하고 랭크를 반영한다.

    Returns:
        플레이어 id -> 랭크 변동(dict). 경쟁전이 아니거나 랭크 조건이 아니면 빈 dict.
        호출부가 이 값을 그대로 WS `rank_update` 로 흘려보낸다.
    """
    parts = sorted(outcome.participants, key=lambda p: p.slot)
    eligible = outcome.rank_eligible()
    season = await active_season(session) if eligible else None

    match = Match(
        season_id=season.id if season else None,
        ranked=eligible,
        mode=outcome.mode,
        room_code=outcome.room_code[:8],
        map_id=outcome.map_id[:32],
        rounds=max(0, outcome.rounds),
        duration_sec=max(0, outcome.duration_sec),
        winner_account_id=next((p.account_id for p in parts if p.won and p.account_id), None),
        forfeit=outcome.forfeit,
    )
    session.add(match)
    await session.flush()

    # 랭크 계산은 **양쪽의 변동 전 상태**를 먼저 다 읽어 둔 뒤에 한다. 한 명을 먼저
    # 갱신하고 그 값으로 상대를 계산하면 먼저 처리된 쪽이 유리해진다.
    profiles: dict[int, RankProfile] = {}
    befores: dict[int, ranked.RankState] = {}
    if eligible and season is not None:
        for part in parts:
            assert part.account_id is not None  # rank_eligible() 이 보장한다
            profile = await ensure_profile(session, part.account_id, season)
            profiles[part.slot] = profile
            befores[part.slot] = to_state(profile)

    changes: dict[str, dict[str, Any]] = {}
    for index, part in enumerate(parts):
        opponent = parts[1 - index] if len(parts) == 2 else None
        opponent_score = opponent.score if opponent else 0

        row = MatchParticipant(
            match_id=match.id,
            slot=part.slot,
            account_id=part.account_id,
            nickname=(part.nickname or "익명")[:16],
            won=part.won,
            score=max(0, part.score),
            opponent_score=max(0, opponent_score),
            coins_earned=max(0, part.coins_earned),
        )

        if part.slot in profiles and opponent is not None:
            change = ranked.apply_match(
                befores[part.slot],
                opponent_mmr=befores[opponent.slot].mmr,
                won=part.won,
                score=part.score,
                opponent_score=opponent_score,
            )
            _apply_to_profile(
                profiles[part.slot], change, score=part.score, opponent_score=opponent_score
            )
            row.tier_before = change.before.tier
            row.rr_before = change.before.rr
            row.tier_after = change.after.tier
            row.rr_after = change.after.rr
            row.rr_delta = change.rr_delta
            row.placement = change.placement
            changes[part.player_id] = change.to_dict()

        session.add(row)

        # 계정 전체 전적/코인은 일반전에서도 갱신한다(경쟁전만의 값이 아니다).
        # 인게임에서 번 코인이 계정 잔액에 실제로 더해지는 지점도 여기 하나뿐이다.
        if part.account_id:
            await account_service.record_match_result(
                session,
                part.account_id,
                won=part.won,
                coins_earned=max(0, part.coins_earned),
            )

    await session.flush()
    return changes


# --------------------------------------------------------------------------
# 조회
# --------------------------------------------------------------------------


async def leaderboard(
    session: AsyncSession, season_id: int, *, limit: int = LEADERBOARD_LIMIT
) -> list[dict[str, Any]]:
    """티어·RR 내림차순. 배치를 마친(tier > 0) 사람만 오른다."""
    limit = max(1, min(LEADERBOARD_LIMIT, int(limit)))
    rows = await session.execute(
        select(RankProfile, Account.nickname, Account.customization)
        .join(Account, Account.id == RankProfile.account_id)
        .where(RankProfile.season_id == season_id, RankProfile.tier > 0)
        .order_by(RankProfile.tier.desc(), RankProfile.rr.desc(), RankProfile.updated_at)
        .limit(limit)
    )
    return [
        {
            "position": i,
            "account_id": profile.account_id,
            "nickname": nickname or "익명",
            "customization": customization or {},
            "rank": public_rank(profile),
        }
        for i, (profile, nickname, customization) in enumerate(rows.all(), start=1)
    ]


async def position_of(session: AsyncSession, profile: RankProfile) -> int | None:
    """리더보드에서 몇 등인가. 배치 중이면 None."""
    if profile.tier <= 0:
        return None
    higher = await session.scalar(
        select(func.count())
        .select_from(RankProfile)
        .where(
            RankProfile.season_id == profile.season_id,
            RankProfile.tier > 0,
            (RankProfile.tier > profile.tier)
            | ((RankProfile.tier == profile.tier) & (RankProfile.rr > profile.rr)),
        )
    )
    return int(higher or 0) + 1


async def history(
    session: AsyncSession,
    account_id: str,
    *,
    limit: int = HISTORY_DEFAULT,
    ranked_only: bool = False,
) -> list[dict[str, Any]]:
    """내 최근 매치. 상대 이름까지 붙여서 화면이 그대로 그릴 수 있는 모양으로 준다."""
    limit = max(1, min(HISTORY_MAX, int(limit)))
    stmt = (
        select(MatchParticipant, Match)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(MatchParticipant.account_id == account_id)
        .order_by(Match.ended_at.desc())
        .limit(limit)
    )
    if ranked_only:
        stmt = stmt.where(Match.ranked.is_(True))

    rows = list((await session.execute(stmt)).all())
    if not rows:
        return []

    # 상대 이름은 같은 매치의 다른 slot 에서 가져온다(한 번에 조회한다).
    match_ids = [match.id for _, match in rows]
    others = await session.scalars(
        select(MatchParticipant).where(
            MatchParticipant.match_id.in_(match_ids),
            MatchParticipant.account_id != account_id,
        )
    )
    opponents: dict[str, MatchParticipant] = {}
    for row in others.all():
        opponents.setdefault(row.match_id, row)

    out: list[dict[str, Any]] = []
    for mine, match in rows:
        rival = opponents.get(match.id)
        out.append(
            {
                "id": match.id,
                "ranked": match.ranked,
                "mode": match.mode,
                "map_id": match.map_id,
                "rounds": match.rounds,
                "duration_sec": match.duration_sec,
                "forfeit": match.forfeit,
                "ended_at": match.ended_at,
                "won": mine.won,
                "score": mine.score,
                "opponent_score": mine.opponent_score,
                "opponent_nickname": (rival.nickname if rival else "") or "상대 없음",
                "rr_delta": mine.rr_delta,
                "placement": mine.placement,
                "tier_before": mine.tier_before,
                "tier_after": mine.tier_after,
                "rr_after": mine.rr_after,
            }
        )
    return out


def public_rank(profile: RankProfile) -> dict[str, Any]:
    """응답에 실어도 되는 랭크 값. **mmr 은 절대 넣지 않는다.**

    숨은 점수가 보이는 순간 사람들은 티어가 아니라 그 숫자를 보고 놀게 되고,
    "왜 이겼는데 RR 이 적게 올랐냐"는 질문이 계산식 폭로전으로 바뀐다.
    """
    return {
        "tier": profile.tier,
        "rr": profile.rr,
        "placements": profile.placements,
        "placement_total": ranked.PLACEMENT_MATCHES,
        "placed": profile.tier > 0,
        "peak_tier": profile.peak_tier,
        "peak_rr": profile.peak_rr,
        "wins": profile.wins,
        "losses": profile.losses,
        "streak": profile.streak,
        "best_streak": profile.best_streak,
        "rounds_won": profile.rounds_won,
        "rounds_lost": profile.rounds_lost,
    }
