"""경쟁전 시즌(발로란트의 '액트') — 조회와 전환.

활성 시즌은 항상 최대 하나다. 시즌이 바뀌면 랭크는 배치부터 다시 보지만, 지난 시즌의
`RankProfile` 행은 지우지 않는다 — 그게 "그때 무슨 티어였는지"의 기록이다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ranked_models import Season

#: 첫 시즌. 마이그레이션이 같은 값을 미리 넣어 두지만, 그 행이 없는 DB(테스트의
#: create_all 경로 등)에서도 서버가 스스로 만들 수 있어야 한다.
FIRST_SEASON_KEY = "act-1"
FIRST_SEASON_NAME = "액트 1"


async def active_season(session: AsyncSession) -> Season:
    """지금 랭크가 걸리는 시즌. 없으면 첫 시즌을 만들어서 돌려준다."""
    season = await session.scalar(
        select(Season).where(Season.is_active.is_(True)).order_by(Season.id.desc()).limit(1)
    )
    if season is not None:
        return season

    season = Season(key=FIRST_SEASON_KEY, name=FIRST_SEASON_NAME, is_active=True)
    session.add(season)
    await session.flush()
    return season


async def list_seasons(session: AsyncSession) -> list[Season]:
    rows = await session.scalars(select(Season).order_by(Season.id.desc()))
    return list(rows.all())


async def start_next_season(session: AsyncSession, key: str, name: str) -> Season:
    """지금 시즌을 닫고 새 시즌을 연다.

    지난 시즌의 `rank_profiles` 행은 **그대로 둔다** — 그게 "그때 무슨 티어였는지"의
    기록이다. 새 시즌 프로필은 각자가 첫 경쟁전을 눌렀을 때 `soft_reset` 을 거쳐 생긴다.
    """
    now = dt.datetime.now(dt.timezone.utc)
    current = await session.scalar(select(Season).where(Season.is_active.is_(True)))
    if current is not None:
        current.is_active = False
        current.ended_at = now

    season = Season(key=key, name=name, is_active=True)
    session.add(season)
    await session.flush()
    return season
