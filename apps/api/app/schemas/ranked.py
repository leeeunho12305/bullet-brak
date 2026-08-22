"""경쟁전 REST 응답 모델 (PROTOCOL §1.2).

`messages.py` 와 나눠 둔 이유는 길이뿐이다(파일당 400줄).

**숨은 MMR 은 어떤 모델에도 없다.** 그 숫자가 보이는 순간 사람들은 티어가 아니라
그걸 보고 놀게 되고, "왜 이겼는데 RR 이 조금 올랐냐"가 계산식 폭로전이 된다.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class TierResponse(BaseModel):
    """티어 한 칸의 표시 정보. 프런트가 뱃지를 그릴 때 쓴다."""

    index: int
    group: str
    group_name: str
    #: 1~3. 디비전이 없는 계급(레디언트)은 0.
    division: int
    name: str
    color: str


class SeasonResponse(BaseModel):
    id: int
    key: str
    name: str
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    is_active: bool


class RankStats(BaseModel):
    """한 시즌의 랭크 상태. 배치 중이면 `placed=False` 이고 tier/rr 은 의미가 없다."""

    #: 1~25. 0 이면 아직 배치 중이다.
    tier: int = 0
    rr: int = 0
    placements: int = 0
    placement_total: int = 5
    placed: bool = False
    peak_tier: int = 0
    peak_rr: int = 0
    wins: int = 0
    losses: int = 0
    #: 양수면 연승, 음수면 연패.
    streak: int = 0
    best_streak: int = 0
    rounds_won: int = 0
    rounds_lost: int = 0


class MyRankResponse(BaseModel):
    """`GET /api/ranked/me`. 아직 한 판도 안 했으면 rank 는 전부 기본값이다."""

    season: SeasonResponse
    rank: RankStats
    #: 리더보드 순위. 배치 중이면 None.
    position: int | None = None


class LeaderboardEntry(BaseModel):
    position: int
    account_id: str
    nickname: str
    customization: dict = Field(default_factory=dict)
    rank: RankStats


class LeaderboardResponse(BaseModel):
    season: SeasonResponse
    entries: list[LeaderboardEntry] = Field(default_factory=list)


class MatchHistoryEntry(BaseModel):
    """전적 한 줄. 경쟁전이 아니면 rr_delta 는 0 이다."""

    id: str
    ranked: bool
    mode: str
    map_id: str
    rounds: int
    duration_sec: int
    #: 상대가 도중에 나가서 끝난 판.
    forfeit: bool
    ended_at: dt.datetime
    won: bool
    score: int
    opponent_score: int
    opponent_nickname: str
    rr_delta: int = 0
    #: 배치전 중이었던 판. RR 대신 "배치 n/5" 로 보여 준다.
    placement: bool = False
    tier_before: int = 0
    tier_after: int = 0
    rr_after: int = 0


class MatchHistoryResponse(BaseModel):
    entries: list[MatchHistoryEntry] = Field(default_factory=list)
