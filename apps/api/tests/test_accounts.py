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


# --------------------------------------------------------------------------
# 로그인 — 아이디 / 비밀번호
# --------------------------------------------------------------------------


def test_login_id_normalizes_case() -> None:
    """대소문자를 구분하면 "만들 때와 다르게 쳤다"는 이유로 못 들어오게 된다."""
    assert account_service.normalize_login_id("MinSu_99") == "minsu_99"
    assert account_service.normalize_login_id("  minsu  ") == "minsu"


def test_login_id_rejects_bad_shapes() -> None:
    assert account_service.normalize_login_id("ab") is None  # 너무 짧다
    assert account_service.normalize_login_id("9minsu") is None  # 숫자로 시작
    assert account_service.normalize_login_id("min su") is None  # 공백
    assert account_service.normalize_login_id("민수") is None  # 한글
    assert account_service.normalize_login_id("a" * 21) is None  # 너무 길다
    assert account_service.normalize_login_id(None) is None


def test_password_rules() -> None:
    assert account_service.password_problem("f7#kQ2mz") is None
    assert account_service.password_problem("short7") is not None
    assert account_service.password_problem("password") is not None  # 흔한 값
    assert account_service.password_problem("aaaaaaaa") is not None  # 한 글자 반복
    # 아이디와 같은 비밀번호는 아이디를 아는 사람에게 그냥 열어 주는 것이다.
    assert account_service.password_problem("minsu123", "minsu123") is not None


async def test_password_is_hashed_not_stored(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        ok, reason, _ = await account_service.set_credentials(s, account, "minsu", "f7#kQ2mz")
        assert (ok, reason) == (True, "ok")
        account_id = account.id

    async with db_session.session_scope() as s:
        row = await s.get(Account, account_id)
        assert row is not None
        assert row.password_hash is not None
        assert "f7#kQ2mz" not in row.password_hash
        assert row.password_hash.startswith("$2b$")


async def test_long_password_is_not_silently_truncated(db) -> None:
    """bcrypt 는 72바이트에서 자른다. 한글은 글자당 3바이트라 24자만 넘어도 걸린다.

    앞부분이 같고 뒤 한 글자만 다른 두 비밀번호가 서로 통과하면 안 된다.
    """
    base = "가나다라마바사아자차카타파하거너더러머버서어" * 2  # 44자 = 132바이트
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        await account_service.set_credentials(s, account, "minsu", base + "끝A")

    async with db_session.session_scope() as s:
        assert await account_service.login(s, "minsu", base + "끝B") is None
        assert await account_service.login(s, "minsu", base + "끝A") is not None


async def test_login_returns_a_new_device_token(db) -> None:
    """로그인의 결과물은 세션이 아니라 이 기기의 디바이스 토큰이다."""
    async with db_session.session_scope() as s:
        account, first_token = await account_service.create_anonymous(s, seed_coins=300)
        await account_service.set_credentials(s, account, "minsu", "f7#kQ2mz")
        account_id = account.id

    async with db_session.session_scope() as s:
        result = await account_service.login(s, "minsu", "f7#kQ2mz", label="다른 기기")
        assert result is not None
        account, second_token = result
        assert account.id == account_id
        assert account.coins == 300  # 코인이 그대로 따라온다
        assert second_token != first_token

    # 두 토큰이 모두 살아 있어야 한다 — 기기 두 대를 동시에 쓰는 게 정상이다.
    async with db_session.session_scope() as s:
        first = await account_service.resolve_token(s, first_token)
        second = await account_service.resolve_token(s, second_token)
        assert first is not None and first.id == account_id
        assert second is not None and second.id == account_id


async def test_login_rejects_wrong_password(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        await account_service.set_credentials(s, account, "minsu", "f7#kQ2mz")

    async with db_session.session_scope() as s:
        assert await account_service.login(s, "minsu", "f7#kQ2mZ") is None
        assert await account_service.login(s, "nobody", "f7#kQ2mz") is None


async def test_login_id_is_taken_by_only_one_account(db) -> None:
    async with db_session.session_scope() as s:
        first, _ = await account_service.create_anonymous(s)
        await account_service.set_credentials(s, first, "minsu", "f7#kQ2mz")

    async with db_session.session_scope() as s:
        second, _ = await account_service.create_anonymous(s)
        ok, reason, _ = await account_service.set_credentials(s, second, "MINSU", "zQ8!wp3v")
        assert (ok, reason) == (False, "taken")


async def test_changing_own_password_keeps_the_id(db) -> None:
    """같은 아이디로 다시 부르는 건 비밀번호 변경이다 — taken 이 되면 안 된다."""
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        await account_service.set_credentials(s, account, "minsu", "f7#kQ2mz")
        ok, reason, _ = await account_service.set_credentials(s, account, "minsu", "zQ8!wp3v")
        assert (ok, reason) == (True, "ok")

    async with db_session.session_scope() as s:
        assert await account_service.login(s, "minsu", "f7#kQ2mz") is None  # 옛 비번은 죽는다
        assert await account_service.login(s, "minsu", "zQ8!wp3v") is not None


# --------------------------------------------------------------------------
# 인계 코드
# --------------------------------------------------------------------------


def test_code_normalization_forgives_human_typing() -> None:
    """하이픈·소문자·헷갈리는 글자(O/I/L)를 사용자가 정확히 칠 거라 기대하지 않는다."""
    canonical = account_service.normalize_code("K7M2-9QPX-3W5B")
    assert canonical == "K7M29QPX3W5B"
    assert account_service.normalize_code("k7m2 9qpx 3w5b") == canonical
    # O -> 0, I/L -> 1 로 되돌린다(알파벳에 없는 글자라 정상 코드를 망가뜨리지 않는다).
    assert account_service.normalize_code("OABI2345678Z") == "0AB12345678Z"


def test_code_normalization_rejects_bad_length_or_letters() -> None:
    assert account_service.normalize_code("K7M2-9QPX") is None  # 짧다
    assert account_service.normalize_code("K7M29QPX3W5BX") is None  # 길다
    assert account_service.normalize_code("K7M29QPX3W5U") is None  # U 는 알파벳에 없다
    assert account_service.normalize_code(None) is None


def test_issued_code_is_readable_and_valid() -> None:
    code = account_service.issue_code()
    assert code.count("-") == 2 and len(code) == 14  # "XXXX-XXXX-XXXX"
    assert account_service.normalize_code(code) is not None


async def test_recovery_code_is_never_stored_in_plaintext(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        code = await account_service.issue_recovery_code(s, account)
        account_id = account.id

    async with db_session.session_scope() as s:
        row = await s.get(Account, account_id)
        assert row is not None
        assert row.recovery_code_hash is not None
        assert row.recovery_code_hash != code.replace("-", "")
        assert len(row.recovery_code_hash) == 64


async def test_redeem_code_links_a_new_device(db) -> None:
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s, seed_coins=500)
        code = await account_service.issue_recovery_code(s, account)
        account_id = account.id

    async with db_session.session_scope() as s:
        result = await account_service.redeem_recovery_code(s, code.lower(), label="폰")
        assert result is not None
        found, token = result
        assert found.id == account_id
        assert found.coins == 500
        resolved = await account_service.resolve_token(s, token)
        assert resolved is not None and resolved.id == account_id


async def test_code_survives_being_used(db) -> None:
    """기기를 셋, 넷 붙일 수 있어야 한다 — 코드는 1회용이 아니다."""
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        code = await account_service.issue_recovery_code(s, account)

    async with db_session.session_scope() as s:
        assert await account_service.redeem_recovery_code(s, code) is not None
        assert await account_service.redeem_recovery_code(s, code) is not None


async def test_reissuing_kills_the_previous_code(db) -> None:
    """재발급이 곧 유출됐을 때의 폐기 수단이다."""
    async with db_session.session_scope() as s:
        account, _ = await account_service.create_anonymous(s)
        old = await account_service.issue_recovery_code(s, account)
        new = await account_service.issue_recovery_code(s, account)
        assert old != new

    async with db_session.session_scope() as s:
        assert await account_service.redeem_recovery_code(s, old) is None
        assert await account_service.redeem_recovery_code(s, new) is not None


async def test_unknown_code_is_rejected(db) -> None:
    async with db_session.session_scope() as s:
        assert await account_service.redeem_recovery_code(s, "ZZZZ-ZZZZ-ZZZZ") is None
        assert await account_service.redeem_recovery_code(s, "형식이 틀린 값") is None


# --------------------------------------------------------------------------
# REST — 로그인 / 인계 코드
# --------------------------------------------------------------------------


async def test_signup_promotes_the_current_account(client) -> None:
    """회원가입 화면이 따로 없다. 쓰던 익명 계정에 아이디/비밀번호를 얹는다."""
    created = await client.post("/api/auth/anon", json={"nickname": "쪼꼬", "seed_coins": 250})
    token = created.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    res = await client.post(
        "/api/me/credentials", headers=auth, json={"login_id": "choco", "password": "f7#kQ2mz"}
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["login_id"] == "choco"

    me = await client.get("/api/me", headers=auth)
    assert me.json()["login_id"] == "choco"
    assert me.json()["coins"] == 250  # 승격이지 새 계정이 아니다


async def test_login_from_another_device_keeps_everything(client) -> None:
    created = await client.post("/api/auth/anon", json={"nickname": "쪼꼬", "seed_coins": 250})
    first = created.json()["token"]
    await client.post(
        "/api/me/credentials",
        headers={"Authorization": f"Bearer {first}"},
        json={"login_id": "choco", "password": "f7#kQ2mz"},
    )

    # 다른 기기 — 토큰이 하나도 없는 상태에서 아이디/비번만으로 들어온다.
    res = await client.post("/api/auth/login", json={"login_id": "CHOCO", "password": "f7#kQ2mz"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["token"] != first
    assert body["account"]["coins"] == 250
    assert body["account"]["id"] == created.json()["account"]["id"]


async def test_login_failure_does_not_reveal_which_half_was_wrong(client) -> None:
    created = await client.post("/api/auth/anon", json={})
    await client.post(
        "/api/me/credentials",
        headers={"Authorization": f"Bearer {created.json()['token']}"},
        json={"login_id": "choco", "password": "f7#kQ2mz"},
    )

    wrong_pw = await client.post(
        "/api/auth/login", json={"login_id": "choco", "password": "nope1234"}
    )
    no_such_id = await client.post(
        "/api/auth/login", json={"login_id": "nobody", "password": "f7#kQ2mz"}
    )
    # 사유가 갈리면 그 창구가 "이 아이디는 존재한다"를 알려주는 도구가 된다.
    assert wrong_pw.json() == no_such_id.json() == {
        "ok": False,
        "reason": "invalid_credentials",
        "token": None,
        "account": None,
    }


async def test_weak_password_is_refused_with_a_reason(client) -> None:
    created = await client.post("/api/auth/anon", json={})
    res = await client.post(
        "/api/me/credentials",
        headers={"Authorization": f"Bearer {created.json()['token']}"},
        json={"login_id": "choco", "password": "password"},
    )
    body = res.json()
    assert (body["ok"], body["reason"]) == (False, "weak_password")
    assert body["message"]  # 사용자에게 보여줄 문장이 비어 있으면 안 된다


async def test_recovery_code_round_trip_over_rest(client) -> None:
    created = await client.post("/api/auth/anon", json={"seed_coins": 70})
    auth = {"Authorization": f"Bearer {created.json()['token']}"}

    issued = await client.post("/api/me/recovery-code", headers=auth)
    assert issued.status_code == 201
    code = issued.json()["code"]

    # 코드는 발급 응답에서만 나온다 — 프로필에는 있다/없다만 실린다.
    me = await client.get("/api/me", headers=auth)
    assert me.json()["has_recovery_code"] is True
    assert code not in me.text

    res = await client.post("/api/auth/redeem", json={"code": code.lower()})
    assert res.json()["ok"] is True
    assert res.json()["account"]["coins"] == 70


async def test_login_attempts_are_rate_limited(client) -> None:
    from app.api.auth import login_limiter

    login_limiter.reset()
    try:
        for _ in range(login_limiter.limit):
            res = await client.post(
                "/api/auth/login", json={"login_id": "nobody", "password": "f7#kQ2mz"}
            )
            assert res.status_code == 200  # 틀린 건 장애가 아니라 정상 응답이다

        blocked = await client.post(
            "/api/auth/login", json={"login_id": "nobody", "password": "f7#kQ2mz"}
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After")
    finally:
        # 리미터는 프로세스 전역이라 치우지 않으면 다음 테스트가 막힌다.
        login_limiter.reset()
