"""상점(가격표 + 구매 창구) 테스트.

여기서 지키려는 것은 딱 두 가지다.

1. **가격표가 프런트 카탈로그의 정렬 결과와 같은가.**
   `avatarParts.ts` 는 파일 하단에서 파츠를 tier 로 안정 정렬한다. 즉 인덱스는 그
   정렬 뒤에야 확정된다. 손으로 옮겨 적으면(=소스에 적힌 순서대로 세면) 반드시
   어긋나므로, 아래 테스트는 "정렬 전 순서였다면 나왔을 값"과 다르다는 것까지 본다.
2. **가격이 서버에서만 나오는가.** 클라이언트가 body 에 price/coins 를 끼워 넣어도
   결과가 달라지면 안 된다.

DB 는 test_accounts.py 와 같은 방식으로 메모리 sqlite 를 꽂는다.
"""

from __future__ import annotations

import json

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base as db_base
from app.db import session as db_session
from app.db.models import Account, AccountItem, AuthToken  # noqa: F401  (metadata 등록)
from app.game import shop

# --------------------------------------------------------------------------
# 가격표 (DB 없이 순수 모듈 테스트)
# --------------------------------------------------------------------------

#: 생성물을 그대로 읽어 이름 ↔ 인덱스 대조에 쓴다(shop 모듈은 이름을 노출하지 않는다).
_RAW = json.loads(shop.PRICES_PATH.read_text(encoding="utf-8"))


def _index_of(slot: str, name: str) -> int:
    return _RAW["names"][slot].index(name)


def test_price_table_is_loaded() -> None:
    assert set(shop.CATEGORIES) == {"eyes", "mouths", "details", "details2"}
    assert shop.TIER_PRICE == (0, 30, 80, 150, 250)
    for category in shop.CATEGORIES:
        assert shop.catalog_size(category) > 0


def test_prices_follow_tier_sort_order() -> None:
    """정렬 결과라면 가격은 슬롯 안에서 절대 내려가지 않는다."""
    for category in shop.CATEGORIES:
        prices = [shop.price_of(f"{category}:{i}") for i in range(shop.catalog_size(category))]
        assert None not in prices
        assert prices == sorted(prices)  # type: ignore[type-var]
        assert prices[0] == 0  # 첫 칸은 항상 기본(무료) 파츠다
        assert set(prices) <= set(shop.TIER_PRICE)


def test_price_matches_tier_of_each_part() -> None:
    """index → tier → TIER_PRICE 가 어긋나지 않는지 전수 확인."""
    for category in shop.CATEGORIES:
        for index, tier in enumerate(_RAW["tiers"][category]):
            assert shop.price_of(f"{category}:{index}") == shop.TIER_PRICE[tier]


def test_index_is_post_sort_not_source_order() -> None:
    """정렬 전 순서로 세면 틀린다 — 이 테스트가 그 함정을 지킨다.

    avatarParts.ts 소스에 적힌 순서로는 EYES[2] 가 'Cute'(tier 1 = 30코인)지만,
    tier 정렬 뒤 그 자리는 tier 0 인 'Round' 다.
    """
    assert _RAW["names"]["eyes"][2] == "Round"
    assert shop.price_of("eyes:2") == 0
    assert shop.price_of(f"eyes:{_index_of('eyes', 'Cute')}") == 30


def test_spot_prices_by_part_name() -> None:
    """등급별 대표 파츠 몇 개를 이름으로 찍어 본다(파츠가 추가돼도 안 깨진다)."""
    expected = [
        ("eyes", "Normal", 0),  # tier 0
        ("eyes", "Sleepy", 30),  # tier 1
        ("eyes", "Cool", 80),  # tier 2 (레거시 선글라스)
        ("eyes", "Cyclops", 150),  # tier 3
        ("eyes", "HeartSad", 250),  # tier 4 (조합으로 만들어진 눈)
        ("mouths", "Smile", 0),
        ("mouths", "Kiss", 250),
        ("details", "None", 0),
        ("details", "Cyber", 250),
        ("details2", "None2", 0),
        ("details2", "Bandana", 30),
        ("details2", "Wings", 250),
    ]
    for slot, name, price in expected:
        assert shop.price_of(f"{slot}:{_index_of(slot, name)}") == price, f"{slot}:{name}"


def test_free_parts_are_marked_free() -> None:
    assert shop.is_free("eyes:0") is True
    assert shop.is_free(f"eyes:{_index_of('eyes', 'Cute')}") is False
    # 모르는 키는 "무료"가 아니라 아예 아이템이 아니다.
    assert shop.is_free("colors:0") is False
    assert shop.is_known("colors:0") is False


def test_unknown_keys_have_no_price() -> None:
    last_eye = shop.catalog_size("eyes") - 1
    for key in (
        None,
        "",
        "   ",
        "colors:0",  # 색은 항상 무료 — 구매 대상이 아니다
        "hats:0",  # 없는 카테고리
        "eyes",  # 구분자 없음
        "eyes:",
        ":3",
        "eyes:-1",
        "eyes:1.5",
        "eyes:03",  # 앞자리 0 별칭을 허용하면 같은 파츠가 두 키로 팔린다
        "EYES:0",
        "eyes:0:0",
        f"eyes:{last_eye + 1}",  # 범위 밖
        "eyes:99999",
        "eyes:" + "9" * 60,  # 길이 초과
    ):
        assert shop.price_of(key) is None, key


def test_broken_price_file_does_not_explode(tmp_path) -> None:
    """파일이 깨져도 import 가 죽으면 안 된다 — 빈 표로 내려앉는다."""
    missing = tmp_path / "nope.json"
    assert shop._load(missing) == ({}, ())

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert shop._load(broken) == ({}, ())

    wrong = tmp_path / "wrong.json"
    wrong.write_text('["nope"]', encoding="utf-8")
    assert shop._load(wrong) == ({}, ())


# --------------------------------------------------------------------------
# sqlite 픽스처 (test_accounts.py 와 동일한 패턴)
# --------------------------------------------------------------------------


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


async def _signup(client: httpx.AsyncClient, coins: int = 0) -> dict[str, str]:
    res = await client.post("/api/auth/anon", json={"nickname": "손님", "seed_coins": coins})
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _key_costing(price: int, category: str = "eyes") -> str:
    """정확히 그 가격인 파츠 키 하나를 가격표에서 고른다."""
    for index in range(shop.catalog_size(category)):
        if shop.price_of(f"{category}:{index}") == price:
            return f"{category}:{index}"
    raise AssertionError(f"{category} 에 {price} 코인짜리 파츠가 없다")


# --------------------------------------------------------------------------
# 구매 엔드포인트
# --------------------------------------------------------------------------


async def test_buy_deducts_exact_server_price(client) -> None:
    headers = await _signup(client, coins=500)
    key = _key_costing(150)

    res = await client.post("/api/me/items", headers=headers, json={"item_key": key})
    assert res.status_code == 200
    body = res.json()
    assert (body["ok"], body["reason"]) == (True, "ok")
    assert body["coins"] == 350
    assert body["owned_items"] == [key]

    # 다음 조회에도 그대로 남아 있어야 한다(커밋됐는가).
    me = (await client.get("/api/me", headers=headers)).json()
    assert me["coins"] == 350
    assert me["owned_items"] == [key]


async def test_buy_ignores_client_supplied_price_and_coins(client) -> None:
    """권위 검증 — body 에 뭘 끼워 넣든 서버 가격표가 이긴다."""
    headers = await _signup(client, coins=300)
    key = _key_costing(250)

    res = await client.post(
        "/api/me/items",
        headers=headers,
        json={"item_key": key, "price": 0, "cost": 1, "coins": 999_999, "ok": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["coins"] == 50  # 300 - 250. 클라이언트가 부른 값은 하나도 반영되지 않는다.


async def test_buy_without_enough_coins_is_200_and_charges_nothing(client) -> None:
    headers = await _signup(client, coins=10)
    key = _key_costing(250)

    res = await client.post("/api/me/items", headers=headers, json={"item_key": key})
    assert res.status_code == 200  # 코인 부족은 장애가 아니다
    body = res.json()
    assert (body["ok"], body["reason"]) == (False, "insufficient_coins")
    assert body["coins"] == 10
    assert body["owned_items"] == []

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["coins"] == 10
    assert me["owned_items"] == []


async def test_buying_twice_does_not_charge_twice(client) -> None:
    headers = await _signup(client, coins=500)
    key = _key_costing(150)

    first = (await client.post("/api/me/items", headers=headers, json={"item_key": key})).json()
    second = (await client.post("/api/me/items", headers=headers, json={"item_key": key})).json()

    assert (first["ok"], first["reason"]) == (True, "ok")
    assert (second["ok"], second["reason"]) == (True, "already_owned")
    assert second["coins"] == first["coins"] == 350
    assert second["owned_items"] == [key]


async def test_unknown_items_are_rejected(client) -> None:
    headers = await _signup(client, coins=500)

    for key in ("colors:0", "hats:2", f"eyes:{shop.catalog_size('eyes')}", "eyes:abc"):
        res = await client.post("/api/me/items", headers=headers, json={"item_key": key})
        assert res.status_code == 200, key
        body = res.json()
        assert (body["ok"], body["reason"]) == (False, "invalid_item"), key
        assert body["coins"] == 500
        assert body["owned_items"] == []


async def test_empty_item_key_is_a_validation_error(client) -> None:
    headers = await _signup(client, coins=500)
    res = await client.post("/api/me/items", headers=headers, json={"item_key": ""})
    assert res.status_code == 422
    assert (await client.post("/api/me/items", headers=headers, json={})).status_code == 422


async def test_free_part_costs_nothing(client) -> None:
    """0등급은 원래 전부에게 열려 있다 — 소유 기록만 남고 코인은 그대로."""
    headers = await _signup(client, coins=100)
    key = _key_costing(0, "details2")

    body = (await client.post("/api/me/items", headers=headers, json={"item_key": key})).json()
    assert (body["ok"], body["reason"]) == (True, "ok")
    assert body["coins"] == 100
    assert body["owned_items"] == [key]


async def test_buy_requires_token(client) -> None:
    res = await client.post("/api/me/items", json={"item_key": _key_costing(30)})
    assert res.status_code == 401

    bad = await client.post(
        "/api/me/items",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"item_key": _key_costing(30)},
    )
    assert bad.status_code == 401


async def test_purchase_does_not_leak_between_accounts(client) -> None:
    buyer = await _signup(client, coins=500)
    other = await _signup(client, coins=500)
    key = _key_costing(150)

    await client.post("/api/me/items", headers=buyer, json={"item_key": key})

    mine = (await client.get("/api/me", headers=other)).json()
    assert mine["owned_items"] == []
    assert mine["coins"] == 500


# --------------------------------------------------------------------------
# DB 가 꺼져 있을 때
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def offline_client():
    await db_session.dispose_engine()
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_buy_returns_503_without_db(offline_client) -> None:
    """500 이 아니라 503 이어야 프런트가 '로컬 모드'로 알아듣는다."""
    res = await offline_client.post("/api/me/items", json={"item_key": "eyes:0"})
    assert res.status_code == 503
