"""계정/신원 서비스.

**신원 모델**: 로그인 UI 없이 시작하기 위해 계정은 익명으로 자동 생성된다.
브라우저는 발급받은 디바이스 토큰(불투명 난수)을 localStorage 에 들고 있고,
서버는 그 토큰의 sha256 해시로 계정을 찾는다. 평문 토큰은 저장하지 않는다.

토큰이 곧 비밀번호다. 유출되면 그 계정이 통째로 넘어간다 — 그래서
`Authorization: Bearer` 헤더로만 받고 URL 에는 절대 싣지 않는다.
(WS 는 헤더를 못 붙이므로 첫 `join` 메시지 본문으로 받는다. 쿼리스트링은
서버 액세스 로그에 남기 때문에 쓰지 않는다.)

여기 있는 함수는 전부 저빈도 경로(REST, WS 입장, 매치 종료)에서만 호출된다.
**60Hz 틱 루프에서는 절대 부르지 않는다.**
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AccountItem, AuthToken

logger = logging.getLogger(__name__)

#: 토큰 바이트 수. urlsafe_b64 라 문자열 길이는 이보다 길다.
TOKEN_BYTES = 32

#: 코인 상한. 오버플로/이상값 방어용이며 게임 밸런스와는 무관하다.
MAX_COINS = 10_000_000


def issue_token() -> str:
    """새 디바이스 토큰(평문). 이 값은 발급 응답에서 딱 한 번만 나간다."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _clamp_coins(value: int) -> int:
    return max(0, min(MAX_COINS, int(value)))


# --------------------------------------------------------------------------
# 생성 / 조회
# --------------------------------------------------------------------------


async def create_anonymous(
    session: AsyncSession,
    *,
    nickname: str = "익명",
    customization: dict[str, Any] | None = None,
    seed_coins: int = 0,
    label: str = "",
) -> tuple[Account, str]:
    """익명 계정 + 첫 디바이스 토큰을 만든다.

    `seed_coins` 는 **localStorage 시절 잔액을 한 번 물려받기 위한 값**이다.
    클라이언트가 보낸 숫자라 위조 가능하므로 호출부에서 `ACCOUNT_SEED_COINS_MAX`
    로 잘라서 넘긴다. 기존 플레이어 이관이 끝나면 그 설정을 0 으로 내리면 된다.

    Returns:
        (계정, 평문 토큰) — 평문 토큰은 여기서만 볼 수 있다.
    """
    account = Account(
        nickname=(nickname or "익명").strip()[:16] or "익명",
        customization=customization or {},
        coins=_clamp_coins(seed_coins),
    )
    session.add(account)
    await session.flush()  # account.id 확정

    token = issue_token()
    session.add(
        AuthToken(
            token_hash=hash_token(token),
            account_id=account.id,
            label=(label or "")[:64],
        )
    )
    await session.flush()
    return account, token


async def resolve_token(session: AsyncSession, token: str | None) -> Account | None:
    """토큰 -> 계정. 없거나 모르는 토큰이면 None.

    조회에 성공하면 `last_used_at` / `last_seen_at` 을 갱신한다(휴면 계정 정리용).
    """
    if not token:
        return None

    row = await session.get(AuthToken, hash_token(token))
    if row is None:
        return None

    now = _utcnow()
    row.last_used_at = now
    row.account.last_seen_at = now
    return row.account


async def issue_additional_token(
    session: AsyncSession, account: Account, *, label: str = ""
) -> str:
    """같은 계정에 토큰을 하나 더 붙인다(다른 기기 연결용). 평문 토큰을 돌려준다."""
    token = issue_token()
    session.add(
        AuthToken(
            token_hash=hash_token(token),
            account_id=account.id,
            label=(label or "")[:64],
        )
    )
    await session.flush()
    return token


# --------------------------------------------------------------------------
# 프로필 / 재화 / 소유권
# --------------------------------------------------------------------------


async def update_profile(
    session: AsyncSession,
    account: Account,
    *,
    nickname: str | None = None,
    customization: dict[str, Any] | None = None,
) -> Account:
    """닉네임/아바타 갱신. 코인은 여기서 건드릴 수 없다(클라이언트가 못 정한다)."""
    if nickname is not None:
        account.nickname = nickname.strip()[:16] or "익명"
    if customization is not None:
        account.customization = customization
    account.last_seen_at = _utcnow()
    return account


async def owned_keys(session: AsyncSession, account_id: str) -> set[str]:
    rows = await session.scalars(
        select(AccountItem.item_key).where(AccountItem.account_id == account_id)
    )
    return set(rows.all())


async def add_coins(session: AsyncSession, account: Account, delta: int) -> int:
    """코인 증감. 음수로 내려가지 않는다. 갱신된 잔액을 돌려준다."""
    account.coins = _clamp_coins(account.coins + int(delta))
    return account.coins


async def buy_item(
    session: AsyncSession, account: Account, item_key: str, price: int
) -> tuple[bool, str]:
    """서버 권위 구매. 가격 판정과 차감이 한 트랜잭션 안에서 일어난다.

    Returns:
        (성공 여부, 실패 사유). 이미 갖고 있으면 (True, "already_owned").
    """
    key = (item_key or "").strip()[:48]
    if not key:
        return False, "invalid_item"

    existing = await session.get(AccountItem, (account.id, key))
    if existing is not None:
        return True, "already_owned"

    price = max(0, int(price))
    if account.coins < price:
        return False, "insufficient_coins"

    account.coins -= price
    session.add(AccountItem(account_id=account.id, item_key=key, paid=price))
    await session.flush()
    return True, "ok"


async def record_match_result(
    session: AsyncSession, account_id: str, *, won: bool, coins_earned: int = 0
) -> None:
    """매치 종료 시 전적/보상 기록.

    ⚠ 틱 루프가 아니라 **매치가 끝난 뒤** 한 번만 호출한다(docs/DEPLOYMENT.md Phase 4).
    """
    await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(
            matches_played=Account.matches_played + 1,
            matches_won=Account.matches_won + (1 if won else 0),
            coins=Account.coins + max(0, int(coins_earned)),
            last_seen_at=_utcnow(),
        )
    )
