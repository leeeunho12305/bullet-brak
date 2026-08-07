"""계정/신원 레이어 테스트.

Postgres 없이 돈다 — 메모리 sqlite 에 `Base.metadata` 로 스키마를 만들어 쓴다.
(alembic 마이그레이션 자체는 Postgres 전용 타입이 없어서 sqlite 에서도 돌지만,
 여기서 검증하려는 건 마이그레이션이 아니라 서비스/라우터 동작이다.)
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import normalize_database_url
from app.db import base as db_base
from app.db import session as db_session
from app.db.models import Account, AccountItem, AuthToken  # noqa: F401  (metadata 등록)
from app.schemas.messages import JoinMsg
from app.services import accounts as account_service

# --------------------------------------------------------------------------
# DB URL 정규화 — 배포처마다 다른 문자열을 하나로 맞추는 부분
# --------------------------------------------------------------------------


def test_render_style_url_gets_asyncpg_driver() -> None:
    """Render 의 fromDatabase 는 드라이버 없는 postgresql:// 를 준다."""
    url, args = normalize_database_url("postgresql://u:p@dpg-abc/bulletbrak")
    assert url == "postgresql+asyncpg://u:p@dpg-abc/bulletbrak"
    assert args == {}


def test_legacy_postgres_scheme_is_upgraded() -> None:
    url, _ = normalize_database_url("postgres://u:p@h:5432/db")
    assert url.startswith("postgresql+asyncpg://")


def test_sslmode_moves_to_connect_args() -> None:
    """asyncpg 는 sslmode 를 모른다. URL 에서 떼어내 ssl 인자로 옮겨야 한다."""
    url, args = normalize_database_url("postgresql://u:p@h/db?sslmode=require")
    assert "sslmode" not in url
    assert args == {"ssl": "require"}


def test_unknown_query_params_are_kept() -> None:
    url, _ = normalize_database_url("postgresql://u:p@h/db?application_name=x&foo=bar")
    # application_name 은 libpq 전용이라 빠지고, 모르는 키는 살려 둔다.
    assert "application_name" not in url
    assert "foo=bar" in url


def test_explicit_driver_is_left_alone() -> None:
    url, _ = normalize_database_url("postgresql+asyncpg://u:p@db:5432/bulletbrak")
    assert url == "postgresql+asyncpg://u:p@db:5432/bulletbrak"


def test_empty_url_is_noop() -> None:
    assert normalize_database_url("") == ("", {})


# --------------------------------------------------------------------------
# sqlite 픽스처
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """메모리 sqlite 엔진을 app.db.session 에 꽂는다. 테스트마다 새 스키마."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,  # 메모리 DB 는 커넥션이 하나여야 같은 스키마를 본다
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


# --------------------------------------------------------------------------
# 서비스
# --------------------------------------------------------------------------


async def test_token_is_never_stored_in_plaintext(db) -> None:
    async with db_session.session_scope() as s:
        _, token = await account_service.create_anonymous(s, nickname="테스터")

    async with db_session.session_scope() as s:
        row = await s.get(AuthToken, account_service.hash_token(token))
        assert row is not None
        # 평문이 그대로 들어간 게 아니어야 한다
        assert row.token_hash != token
        assert len(row.token_hash) == 64


async def test_resolve_token_roundtrip(db) -> None:
    async with db_session.session_scope() as s:
        account, token = await account_service.create_anonymous(s, nickname="루피")
        account_id = account.id

    async with db_session.session_scope() as s:
        found = await account_service.resolve_token(s, token)
        assert found is not None
        assert found.id == account_id
        assert found.nickname == "루피"


async def test_unknown_token_resolves_to_none(db) -> None:
    async with db_session.session_scope() as s:
        assert await account_service.resolve_token(s, "존재하지-않는-토큰") is None
        assert await account_service.resolve_token(s, None) is None


async def test_seed_coins_are_clamped_by_caller_contract(db) -> None:
    """서비스 자체는 넘어온 값을 그대로 쓴다 — 자르는 책임은 라우터에 있다.

    (라우터가 ACCOUNT_SEED_COINS_MAX 로 min() 하는 것을 아래 REST 테스트가 확인한다.)
    """
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s, seed_coins=500)
        assert account.coins == 500


async def test_buy_item_deducts_and_grants(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s, seed_coins=100)
        ok, reason = await account_service.buy_item(s, account, "eyes:3", 30)
        assert (ok, reason) == (True, "ok")
        assert account.coins == 70
        assert await account_service.owned_keys(s, account.id) == {"eyes:3"}


async def test_buy_item_rejects_when_broke(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s, seed_coins=10)
        ok, reason = await account_service.buy_item(s, account, "eyes:3", 30)
        assert (ok, reason) == (False, "insufficient_coins")
        assert account.coins == 10  # 실패했으면 차감도 없어야 한다
        assert await account_service.owned_keys(s, account.id) == set()


async def test_buy_item_is_idempotent(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s, seed_coins=100)
        await account_service.buy_item(s, account, "eyes:3", 30)
        ok, reason = await account_service.buy_item(s, account, "eyes:3", 30)
        assert (ok, reason) == (True, "already_owned")
        assert account.coins == 70  # 두 번 결제되면 안 된다


async def test_match_result_updates_record(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        account_id = account.id

    async with db_session.session_scope() as s:
        await account_service.record_match_result(s, account_id, won=True, coins_earned=50)
        await account_service.record_match_result(s, account_id, won=False, coins_earned=10)

    async with db_session.session_scope() as s:
        account = await s.get(Account, account_id)
        assert account is not None
        assert (account.matches_played, account.matches_won) == (2, 1)
        assert account.coins == 60


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------


async def test_health_reports_db_on(client) -> None:
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "on"}


async def test_anon_signup_then_me(client) -> None:
    res = await client.post(
        "/api/auth/anon",
        json={"nickname": "쪼꼬", "seed_coins": 250, "seed_items": ["eyes:3", "mouths:1"]},
    )
    assert res.status_code == 201
    body = res.json()
    token = body["token"]
    assert body["account"]["nickname"] == "쪼꼬"
    assert body["account"]["coins"] == 250
    assert body["account"]["owned_items"] == ["eyes:3", "mouths:1"]

    me = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["account"]["id"]


async def test_seed_coins_are_capped_by_setting(client, monkeypatch) -> None:
    """localStorage 잔액은 위조 가능하다. 상한을 넘겨 받으면 안 된다."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "account_seed_coins_max", 1000, raising=False)

    res = await client.post("/api/auth/anon", json={"seed_coins": 9_999_999})
    assert res.status_code == 201
    assert res.json()["account"]["coins"] == 1000


async def test_me_requires_valid_token(client) -> None:
    assert (await client.get("/api/me")).status_code == 401
    # 헤더는 ASCII 만 실린다 — 한글 토큰은 httpx 가 보내기 전에 막는다.
    bad = await client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad.status_code == 401


async def test_bearer_scheme_is_required(client) -> None:
    res = await client.post("/api/auth/anon", json={})
    token = res.json()["token"]
    # 스킴 없이 토큰만 보내면 인증되면 안 된다
    wrong = await client.get("/api/me", headers={"Authorization": token})
    assert wrong.status_code == 401


async def test_patch_me_cannot_change_coins(client) -> None:
    res = await client.post("/api/auth/anon", json={"seed_coins": 300})
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    patched = await client.patch(
        "/api/me",
        headers=headers,
        json={"nickname": "새이름", "coins": 999_999, "customization": {"eye": 2}},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["nickname"] == "새이름"
    assert body["customization"]["eye"] == 2
    assert body["coins"] == 300  # 클라이언트가 코인을 정할 수 없다


# --------------------------------------------------------------------------
# DB 가 꺼져 있을 때 (DATABASE_URL 없음)
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def offline_client():
    """엔진이 아예 없는 상태. 기존 배포(무DB)와 같은 조건이다."""
    await db_session.dispose_engine()
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_still_200_without_db(offline_client) -> None:
    """Render healthCheckPath 가 DB 때문에 실패하면 배포가 통째로 막힌다."""
    res = await offline_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["db"] == "off"


async def test_account_endpoints_return_503_without_db(offline_client) -> None:
    """500 이 아니라 503 이어야 프런트가 '로컬 모드'로 알아듣는다."""
    assert (await offline_client.post("/api/auth/anon", json={})).status_code == 503
    assert (await offline_client.get("/api/me")).status_code == 503


async def test_game_endpoints_work_without_db(offline_client) -> None:
    """DB 가 없어도 게임 자체는 굴러가야 한다."""
    res = await offline_client.post("/api/rooms", json={"mode": "pvp", "max_players": 2})
    assert res.status_code == 201


# --------------------------------------------------------------------------
# WS 입장 시 신원 반영
# --------------------------------------------------------------------------


async def test_join_uses_account_coins_not_client_value(db) -> None:
    """클라이언트가 코인을 신고해도 로그인 상태면 계정 잔액이 이긴다."""
    from app.api.ws import _create_player, _load_identity
    from app.game.rooms import room_manager

    async with db_session.session_scope() as s:
        _, token = await account_service.create_anonymous(s, nickname="주인", seed_coins=42)

    identity = await _load_identity(token)
    assert identity is not None

    room = room_manager.create(mode="pvp", max_players=2)
    join = JoinMsg.model_validate({"nickname": "주인", "coins": 9_999_999, "token": token})
    player = _create_player(room, join, "", identity)

    assert player.coins == 42
    assert player.account_id == identity.account_id


async def test_join_without_token_stays_anonymous(db) -> None:
    from app.api.ws import _create_player, _load_identity
    from app.game.rooms import room_manager

    identity = await _load_identity(None)
    assert identity is None

    room = room_manager.create(mode="pvp", max_players=2)
    join = JoinMsg.model_validate({"nickname": "손님", "coins": 77})
    player = _create_player(room, join, "", identity)

    # 비로그인은 예전 동작 그대로 — 클라이언트 값을 쓰고 계정에 묶이지 않는다.
    assert player.coins == 77
    assert player.account_id is None


async def test_bad_token_falls_back_to_anonymous(db) -> None:
    """모르는 토큰으로 입장이 막히면 안 된다(그냥 비로그인 취급)."""
    from app.api.ws import _load_identity

    assert await _load_identity("쓰레기토큰") is None
