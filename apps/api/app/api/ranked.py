"""경쟁전 REST — `/api/ranked/*` (PROTOCOL §1.2).

DB 가 꺼져 있으면 계정 API 와 같은 규칙을 따른다: **503**. 프런트는 그 값을 보고
경쟁전 자체를 감춘다(랭크는 기록이 남아야 뜻이 있는데, DB 가 없으면 남길 곳이 없다).

`/api/ranked/tiers` 만 예외로 DB 없이도 200 이다 — 티어 표는 코드 상수라서
DB 와 무관하고, 프런트가 부팅할 때 한 번 받아 캐시해 두는 값이다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_account, db_session
from app.db.models import Account
from app.schemas.ranked import (
    LeaderboardEntry,
    LeaderboardResponse,
    MatchHistoryResponse,
    MyRankResponse,
    RankStats,
    SeasonResponse,
    TierResponse,
)
from app.services import matches as match_service
from app.services import ranked

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ranked", tags=["ranked"])


@router.get("/tiers", response_model=list[TierResponse])
async def get_tiers() -> list[dict]:
    """티어 표(아이언 1 ~ 레디언트). 코드 상수라 DB 가 없어도 200 이다.

    프런트가 뱃지 색과 이름을 여기서 받아 간다 — 같은 표를 양쪽에 적어 두면
    반드시 어긋나기 때문에 서버가 유일한 원본이다.
    """
    return ranked.tier_catalog()


@router.get("/seasons", response_model=list[SeasonResponse])
async def get_seasons(session: AsyncSession = Depends(db_session)) -> list[SeasonResponse]:
    seasons = await match_service.list_seasons(session)
    if not seasons:
        # 아직 아무 시즌도 없으면 첫 시즌을 여기서 연다(마이그레이션이 넣어 두지만,
        # create_all 로 만든 스키마에는 그 행이 없다).
        seasons = [await match_service.active_season(session)]
    return [SeasonResponse.model_validate(s, from_attributes=True) for s in seasons]


@router.get("/me", response_model=MyRankResponse)
async def get_my_rank(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> MyRankResponse:
    """내 랭크. 경쟁전을 한 번도 안 했으면 프로필이 없으므로 기본값을 돌려준다.

    **여기서 프로필 행을 만들지 않는다** — 로비를 열었다는 이유만으로 리더보드
    후보가 생기면 안 된다. 행은 첫 경쟁전이 끝날 때 생긴다.
    """
    season = await match_service.active_season(session)
    profile = await match_service.get_profile(session, account.id, season.id)

    if profile is None:
        return MyRankResponse(
            season=SeasonResponse.model_validate(season, from_attributes=True),
            rank=RankStats(placement_total=ranked.PLACEMENT_MATCHES),
            position=None,
        )

    return MyRankResponse(
        season=SeasonResponse.model_validate(season, from_attributes=True),
        rank=RankStats(**match_service.public_rank(profile)),
        position=await match_service.position_of(session, profile),
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    season_id: int | None = Query(default=None),
    limit: int = Query(default=match_service.LEADERBOARD_LIMIT, ge=1, le=200),
    session: AsyncSession = Depends(db_session),
) -> LeaderboardResponse:
    """티어·RR 순위표. 배치를 마친 사람만 오른다.

    로그인 여부와 무관하게 볼 수 있다(순위표는 공개 정보다). 내 순위를 함께 표시하는
    일은 프런트가 `/api/ranked/me` 로 따로 한다 — 여기에 인증을 걸면 비로그인 상태에서
    순위표조차 못 보게 된다.
    """
    season = (
        await match_service.active_season(session)
        if season_id is None
        else await _season_or_active(session, season_id)
    )
    rows = await match_service.leaderboard(session, season.id, limit=limit)
    return LeaderboardResponse(
        season=SeasonResponse.model_validate(season, from_attributes=True),
        entries=[LeaderboardEntry(**row) for row in rows],
    )


@router.get("/matches", response_model=MatchHistoryResponse)
async def get_my_matches(
    limit: int = Query(default=match_service.HISTORY_DEFAULT, ge=1, le=match_service.HISTORY_MAX),
    ranked_only: bool = Query(default=False),
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> MatchHistoryResponse:
    """내 최근 전적. 기본은 일반전까지 전부, `ranked_only=true` 면 경쟁전만."""
    entries = await match_service.history(
        session, account.id, limit=limit, ranked_only=ranked_only
    )
    return MatchHistoryResponse(entries=entries)


async def _season_or_active(session: AsyncSession, season_id: int):
    """모르는 시즌 id 는 404 대신 활성 시즌으로 되돌린다.

    순위표는 링크로 오가는 화면이라, 지난 시즌 링크가 죽었다고 빈 에러 페이지를
    보여 주는 것보다 지금 시즌을 보여 주는 편이 낫다.
    """
    from app.db.ranked_models import Season

    season = await session.get(Season, season_id)
    return season if season is not None else await match_service.active_season(session)
