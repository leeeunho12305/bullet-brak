"""매치 기록 / 랭크 반영 — DB 를 끼운 쪽.

`test_accounts.py` 와 같은 방식으로 메모리 sqlite 를 꽂는다. 여기서 확인하려는 것은
"규칙이 계산대로 행에 옮겨졌는가"와 "옮기면 안 되는 판은 안 옮겼는가"다.
"""

from __future__ import annotations

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base as db_base
from app.db import session as db_session
from app.db.models import Account  # noqa: F401  (metadata 등록)
from app.db.ranked_models import Match, MatchParticipant, RankProfile
from app.game.rooms import RoomManager
from app.services import accounts as account_service
from app.services import matches as match_service
from app.services import ranked, results


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(db_base.Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    db_session._install_for_tests(maker, engine)
    try:
        yield maker
    finally:
        await db_session.dispose_engine()


@pytest_asyncio.fixture
async def client(db):
    """lifespan 을 돌리지 않는다 — 돌리면 init_db 가 위 sqlite 엔진을 덮어쓴다."""
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _two_accounts() -> tuple[str, str]:
    async with db_session.session_scope() as s:
        a, _ = await account_service.create_anonymous(s, nickname="가")
        b, _ = await account_service.create_anonymous(s, nickname="나")
        return a.id, b.id


def _outcome(
    a_id: str | None, b_id: str | None, *, ranked_room: bool = True, forfeit: bool = False
) -> match_service.MatchOutcome:
    return match_service.MatchOutcome(
        room_code="123456",
        mode="pvp",
        ranked=ranked_room,
        map_id="classic",
        rounds=13,
        duration_sec=240,
        forfeit=forfeit,
        participants=[
            match_service.ParticipantResult(
                slot=0,
                player_id="p-a",
                account_id=a_id,
                nickname="가",
                score=5,
                won=True,
                coins_earned=150,
            ),
            match_service.ParticipantResult(
                slot=1,
                player_id="p-b",
                account_id=b_id,
                nickname="나",
                score=3,
                won=False,
                coins_earned=30,
            ),
        ],
    )


# --------------------------------------------------------------------------
# 시즌
# --------------------------------------------------------------------------


async def test_active_season_is_created_on_demand(db) -> None:
    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        assert season.is_active is True
        again = await match_service.active_season(s)
        assert again.id == season.id  # 두 번 부른다고 두 개가 생기면 안 된다


async def test_starting_a_new_season_closes_the_old_one(db) -> None:
    async with db_session.session_scope() as s:
        first = await match_service.active_season(s)
        second = await match_service.start_next_season(s, "act-2", "액트 2")
        assert second.id != first.id
        assert first.is_active is False
        assert first.ended_at is not None
        assert (await match_service.active_season(s)).id == second.id


# --------------------------------------------------------------------------
# 기록
# --------------------------------------------------------------------------


async def test_ranked_match_creates_profiles_and_moves_placements(db) -> None:
    a_id, b_id = await _two_accounts()

    async with db_session.session_scope() as s:
        changes = await match_service.record(s, _outcome(a_id, b_id))

    # 배치 첫 판이라 티어는 아직 없고 RR 도 안 움직인다.
    assert set(changes) == {"p-a", "p-b"}
    assert changes["p-a"]["placement"] is True
    assert changes["p-a"]["rr_delta"] == 0
    assert changes["p-a"]["placement_played"] == 1

    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        winner = await match_service.get_profile(s, a_id, season.id)
        loser = await match_service.get_profile(s, b_id, season.id)
        assert winner is not None and loser is not None
        assert (winner.wins, winner.losses, winner.streak) == (1, 0, 1)
        assert (loser.wins, loser.losses, loser.streak) == (0, 1, -1)
        assert winner.mmr > loser.mmr  # 이긴 쪽 숨은 점수가 위로 간다
        assert (winner.rounds_won, winner.rounds_lost) == (5, 3)


async def test_rr_moves_once_placements_are_done(db) -> None:
    a_id, b_id = await _two_accounts()

    # 배치 5판을 채운다.
    for _ in range(ranked.PLACEMENT_MATCHES):
        async with db_session.session_scope() as s:
            await match_service.record(s, _outcome(a_id, b_id))

    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        winner = await match_service.get_profile(s, a_id, season.id)
        assert winner is not None and winner.tier > 0
        before_rr, before_tier = winner.rr, winner.tier

    async with db_session.session_scope() as s:
        changes = await match_service.record(s, _outcome(a_id, b_id))

    assert changes["p-a"]["placement"] is False
    assert changes["p-a"]["rr_delta"] > 0
    assert changes["p-b"]["rr_delta"] < 0

    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        winner = await match_service.get_profile(s, a_id, season.id)
        assert winner is not None
        # 승급했을 수도 있으므로 티어·RR 을 한 축으로 비교한다.
        assert (winner.tier, winner.rr) > (before_tier, before_rr)


async def test_both_sides_are_scored_against_the_same_pre_match_state(db) -> None:
    """한쪽을 먼저 갱신하고 그 값으로 상대를 계산하면 순서가 결과를 바꾼다."""
    a_id, b_id = await _two_accounts()

    async with db_session.session_scope() as s:
        await match_service.record(s, _outcome(a_id, b_id))
        season = await match_service.active_season(s)
        a = await match_service.get_profile(s, a_id, season.id)
        b = await match_service.get_profile(s, b_id, season.id)
        assert a is not None and b is not None
        # 같은 실력에서 시작해 한 판을 주고받았으니 이동량이 대칭이어야 한다.
        assert (a.mmr - ranked.BASE_MMR) == (ranked.BASE_MMR - b.mmr)


async def test_casual_match_is_recorded_without_touching_rank(db) -> None:
    a_id, b_id = await _two_accounts()

    async with db_session.session_scope() as s:
        changes = await match_service.record(s, _outcome(a_id, b_id, ranked_room=False))

    assert changes == {}
    async with db_session.session_scope() as s:
        match = await s.scalar(select(Match))
        assert match is not None and match.ranked is False and match.season_id is None
        assert (await s.scalar(select(RankProfile))) is None
        # 그래도 계정 전적과 코인은 갱신된다.
        account = await s.get(Account, a_id)
        assert account is not None
        assert (account.matches_played, account.matches_won) == (1, 1)
        assert account.coins == 150


async def test_ranked_flag_is_dropped_when_a_side_has_no_account(db) -> None:
    """계정이 없는 사람과의 판에는 랭크를 걸 수 없다 — 기록할 곳이 없다."""
    a_id, _ = await _two_accounts()

    async with db_session.session_scope() as s:
        changes = await match_service.record(s, _outcome(a_id, None))

    assert changes == {}
    async with db_session.session_scope() as s:
        match = await s.scalar(select(Match))
        assert match is not None and match.ranked is False


async def test_forfeit_is_recorded_as_a_loss_for_the_leaver(db) -> None:
    a_id, b_id = await _two_accounts()

    async with db_session.session_scope() as s:
        await match_service.record(s, _outcome(a_id, b_id, forfeit=True))

    async with db_session.session_scope() as s:
        match = await s.scalar(select(Match))
        assert match is not None
        assert match.forfeit is True
        assert match.winner_account_id == a_id
        rows = (await s.scalars(select(MatchParticipant))).all()
        assert {r.account_id: r.won for r in rows} == {a_id: True, b_id: False}


async def test_nickname_is_frozen_at_match_time(db) -> None:
    a_id, b_id = await _two_accounts()
    async with db_session.session_scope() as s:
        await match_service.record(s, _outcome(a_id, b_id))

    async with db_session.session_scope() as s:
        account = await s.get(Account, a_id)
        assert account is not None
        account.nickname = "이름바꿈"

    async with db_session.session_scope() as s:
        rows = await match_service.history(s, b_id)
        assert rows[0]["opponent_nickname"] == "가"  # 그때 이름이 남아 있어야 한다


# --------------------------------------------------------------------------
# 조회
# --------------------------------------------------------------------------


async def test_leaderboard_only_lists_placed_players(db) -> None:
    a_id, b_id = await _two_accounts()

    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        assert await match_service.leaderboard(s, season.id) == []

    for _ in range(ranked.PLACEMENT_MATCHES):
        async with db_session.session_scope() as s:
            await match_service.record(s, _outcome(a_id, b_id))

    async with db_session.session_scope() as s:
        season = await match_service.active_season(s)
        rows = await match_service.leaderboard(s, season.id)
        assert [r["position"] for r in rows] == [1, 2]
        assert rows[0]["account_id"] == a_id  # 5연승 쪽이 위
        assert "mmr" not in rows[0]["rank"]  # 숨은 점수는 새지 않는다

        winner = await match_service.get_profile(s, a_id, season.id)
        assert winner is not None
        assert await match_service.position_of(s, winner) == 1


async def test_history_reads_from_the_players_own_side(db) -> None:
    a_id, b_id = await _two_accounts()
    async with db_session.session_scope() as s:
        await match_service.record(s, _outcome(a_id, b_id))

    async with db_session.session_scope() as s:
        mine = await match_service.history(s, a_id)
        theirs = await match_service.history(s, b_id)

    assert mine[0]["won"] is True and mine[0]["score"] == 5
    assert mine[0]["opponent_nickname"] == "나"
    assert theirs[0]["won"] is False and theirs[0]["score"] == 3
    assert theirs[0]["opponent_nickname"] == "가"


# --------------------------------------------------------------------------
# 방 -> 결과 캡처
# --------------------------------------------------------------------------


def _room_with_two(ranked_room: bool):
    from app.game.models import Player

    manager = RoomManager()
    room = manager.create("pvp", 2, ranked=ranked_room)
    for i, (pid, account) in enumerate((("p-a", "acc-a"), ("p-b", "acc-b"))):
        room.players[pid] = Player(id=pid, nickname=f"P{i}", account_id=account)
        room.scores[pid] = 5 if i == 0 else 2
    room.winner_id = "p-a"
    room.rounds_played = 11
    return room


def test_capture_finish_copies_scores_and_accounts() -> None:
    room = _room_with_two(True)
    outcome = results.capture_finish(room)
    assert outcome is not None
    assert outcome.ranked is True
    assert outcome.rounds == 11
    assert outcome.rank_eligible() is True
    assert [(p.player_id, p.score, p.won) for p in outcome.participants] == [
        ("p-a", 5, True),
        ("p-b", 2, False),
    ]


def test_capture_finish_skips_training_rooms() -> None:
    manager = RoomManager()
    room = manager.create("training", 1)
    assert results.capture_finish(room) is None


def test_capture_forfeit_makes_the_leaver_lose() -> None:
    room = _room_with_two(True)
    leaver = room.players.pop("p-b")
    outcome = results.capture_forfeit(room, leaver)
    assert outcome is not None
    assert outcome.forfeit is True
    assert outcome.rank_eligible() is True
    assert {p.player_id: p.won for p in outcome.participants} == {"p-a": True, "p-b": False}
    # 나간 사람의 점수도 남아 있어야 한다(scores 를 지우기 전에 복사했으므로).
    assert {p.player_id: p.score for p in outcome.participants} == {"p-a": 5, "p-b": 2}


def test_casual_room_has_no_forfeit_penalty() -> None:
    """일반전에서 나가는 건 그냥 나가는 것이다. 벌점이 붙을 이유가 없다."""
    room = _room_with_two(False)
    leaver = room.players.pop("p-b")
    assert results.capture_forfeit(room, leaver) is None


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------


async def test_tier_catalog_endpoint(client) -> None:
    res = await client.get("/api/ranked/tiers")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == ranked.MAX_TIER
    assert body[-1]["name"] == "레디언트"


async def test_my_rank_defaults_before_the_first_ranked_match(client) -> None:
    signup = await client.post("/api/auth/anon", json={"nickname": "새내기"})
    token = signup.json()["token"]

    res = await client.get("/api/ranked/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["rank"]["placed"] is False
    assert body["rank"]["placements"] == 0
    assert body["position"] is None
    assert body["season"]["is_active"] is True
    assert "mmr" not in body["rank"]


async def test_my_rank_requires_a_token(client) -> None:
    assert (await client.get("/api/ranked/me")).status_code == 401


async def test_leaderboard_is_public(client) -> None:
    res = await client.get("/api/ranked/leaderboard")
    assert res.status_code == 200
    assert res.json()["entries"] == []


async def test_unknown_season_falls_back_to_the_active_one(client) -> None:
    res = await client.get("/api/ranked/leaderboard?season_id=9999")
    assert res.status_code == 200
    assert res.json()["season"]["is_active"] is True


async def test_match_history_endpoint(client, db) -> None:
    signup = await client.post("/api/auth/anon", json={"nickname": "가"})
    token = signup.json()["token"]
    a_id = signup.json()["account"]["id"]

    async with db_session.session_scope() as s:
        b, _ = await account_service.create_anonymous(s, nickname="나")
        b_id = b.id
    async with db_session.session_scope() as s:
        await match_service.record(s, _outcome(a_id, b_id))

    res = await client.get(
        "/api/ranked/matches?ranked_only=true", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    entries = res.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["won"] is True
    assert entries[0]["opponent_nickname"] == "나"


async def test_ranked_room_needs_a_database(client) -> None:
    """DB 가 있는 이 픽스처에서는 만들어져야 하고, 인원·맵이 서버 규칙으로 고정된다."""
    res = await client.post(
        "/api/rooms", json={"mode": "pvp", "max_players": 4, "map_id": "classic", "ranked": True}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["ranked"] is True
    assert body["max_players"] == 2
    assert body["map_id"] == "random"


async def test_training_room_cannot_be_ranked(client) -> None:
    res = await client.post("/api/rooms", json={"mode": "training", "ranked": True})
    assert res.status_code == 201
    assert res.json()["ranked"] is False
