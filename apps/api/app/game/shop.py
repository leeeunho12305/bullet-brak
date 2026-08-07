"""파츠 상점 가격표 — 서버 권위의 단일 출처.

가격을 클라이언트가 부르면 그건 권위가 아니라 **연출**이다. 그래서 구매 판정에 쓰는
가격은 오직 이 모듈에서만 나온다(요청 본문의 price 같은 필드는 읽지도 않는다).

가격의 원본은 여전히 프런트 카탈로그다: `apps/web/src/game/avatarParts.ts`.
거기서 파츠는 등급(tier)만 갖고, 파일 하단에서 네 카탈로그가 tier 기준으로 **안정 정렬**
되면서 비로소 "인덱스 → 가격" 이 확정된다(EYES 는 눈모양 × 눈썹 조합이라 더 심하다).
그 표를 손으로 옮겨 적으면 반드시 어긋나므로 `pnpm shop:prices`
(= `scripts/export-shop-prices.mjs`)가 TS 를 실제로 평가해서 옆의 `shop_prices.json`
을 만든다. **JSON 을 직접 고치지 말 것.** 파츠를 추가했다면 스크립트를 다시 돌린다.

아이템 키는 레거시 포맷 그대로 `"{category}:{index}"` 다 (예: `"eyes:12"`).
`colors` 는 항상 무료라 가격표에 없다 — 구매 창구로 들어오면 모르는 카테고리 취급이다.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 생성물 위치. 이 모듈 옆에 있다(패키징할 때 같이 딸려가야 한다).
PRICES_PATH = Path(__file__).with_name("shop_prices.json")

#: 아이템 키 문법. 카테고리는 소문자/숫자, 인덱스는 앞에 0 이 붙지 않은 십진수.
#: ("eyes:03" 같은 별칭을 허용하면 같은 파츠가 두 키로 팔린다.)
_KEY_RE = re.compile(r"^([a-z][a-z0-9_]{0,15}):(0|[1-9][0-9]{0,3})$")

#: 아이템 키 최대 길이. AccountItem.item_key 저장 한계(48)와 맞춰 둔다.
MAX_KEY_LEN = 48


def _load(path: Path) -> tuple[dict[str, tuple[int, ...]], tuple[int, ...]]:
    """가격표를 읽는다. 실패해도 절대 예외를 밖으로 내보내지 않는다.

    여기서 import 가 죽으면 게임 서버 전체가 못 뜬다. 가격표가 없으면 "아무것도
    못 산다"(모든 구매가 invalid_item)로 내려앉는 편이 낫다 — 공짜로 풀리는 것보다.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("상점 가격표가 없다: %s — `pnpm shop:prices` 로 생성할 것", path)
        return {}, ()
    except (OSError, ValueError):
        logger.exception("상점 가격표를 읽지 못했다: %s", path)
        return {}, ()

    if not isinstance(raw, dict):
        logger.error("상점 가격표 형식이 이상하다(최상위가 객체가 아님): %s", path)
        return {}, ()

    slots: dict[str, tuple[int, ...]] = {}
    for category, prices in (raw.get("slots") or {}).items():
        if not isinstance(category, str) or not isinstance(prices, list):
            continue
        try:
            slots[category] = tuple(max(0, int(p)) for p in prices)
        except (TypeError, ValueError):
            logger.error("상점 가격표의 %s 슬롯에 숫자가 아닌 값이 있다", category)

    tier_price = raw.get("tier_price")
    tiers: tuple[int, ...] = ()
    if isinstance(tier_price, list):
        try:
            tiers = tuple(max(0, int(p)) for p in tier_price)
        except (TypeError, ValueError):
            tiers = ()

    if not slots:
        logger.error("상점 가격표가 비어 있다: %s", path)
    return slots, tiers


_SLOTS, TIER_PRICE = _load(PRICES_PATH)

#: 구매 가능한 카테고리(가격표에 실제로 실린 것만).
CATEGORIES: tuple[str, ...] = tuple(sorted(_SLOTS))


def catalog_size(category: str) -> int:
    """해당 카테고리의 파츠 개수. 모르는 카테고리면 0."""
    return len(_SLOTS.get(category, ()))


def price_of(item_key: str | None) -> int | None:
    """아이템 키 → 가격(코인).

    모르는 카테고리 / 범위 밖 인덱스 / 형식 오류면 `None` 이다. 0 을 돌려줄 수도
    있는데(0등급 = 기본 제공), 그건 "공짜"지 "없는 아이템"이 아니다 —
    `None` 과 `0` 을 헷갈리지 말 것. 무료인지 알고 싶으면 `is_free()` 를 쓴다.
    """
    if not item_key or len(item_key) > MAX_KEY_LEN:
        return None
    m = _KEY_RE.match(item_key.strip())
    if m is None:
        return None
    prices = _SLOTS.get(m.group(1))
    if prices is None:
        return None
    index = int(m.group(2))
    if index >= len(prices):
        return None
    return prices[index]


def is_free(item_key: str | None) -> bool:
    """0등급(기본 제공) 파츠인가. 모르는 키는 False(그건 애초에 아이템이 아니다)."""
    return price_of(item_key) == 0


def is_known(item_key: str | None) -> bool:
    """가격표에 실린 아이템인가. 구매 창구가 401/거절을 가르는 기준이다."""
    return price_of(item_key) is not None
