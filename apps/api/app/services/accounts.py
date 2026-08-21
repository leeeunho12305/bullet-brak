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
import re
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, AccountItem, AuthToken
from app.services import passwords

logger = logging.getLogger(__name__)

#: 토큰 바이트 수. urlsafe_b64 라 문자열 길이는 이보다 길다.
TOKEN_BYTES = 32

#: 코인 상한. 오버플로/이상값 방어용이며 게임 밸런스와는 무관하다.
MAX_COINS = 10_000_000

#: 인계 코드 알파벳 — Crockford Base32. I/L/O/U 가 없다.
#: 앞의 셋은 1/0 과 헷갈려서, U 는 우연히 욕설이 만들어지는 걸 막으려고 뺀다.
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: 코드 길이(하이픈 제외). 32^12 ≈ 2^60 — 온라인 무차별 대입으로는 닿을 수 없는 크기다.
CODE_LENGTH = 12

#: 표시할 때 끊어 주는 단위 ("K7M2-9QPX-3W5B")
CODE_GROUP = 4

#: 사람이 옮겨 적다가 흔히 틀리는 글자를 되돌린다. 알파벳에 없는 글자들이라
#: 이 매핑이 정상 코드를 망가뜨릴 일은 없다.
_CODE_CONFUSABLES = str.maketrans({"O": "0", "I": "1", "L": "1"})

#: 로그인 아이디 규칙. 영문 소문자로 시작하고, 소문자/숫자/밑줄만 쓴다.
#: 대소문자를 구분하지 않으려고 저장 전에 소문자로 눌러 두므로 패턴도 소문자만 받는다.
LOGIN_ID_MIN = 4
LOGIN_ID_MAX = 20
_LOGIN_ID_RE = re.compile(rf"^[a-z][a-z0-9_]{{{LOGIN_ID_MIN - 1},{LOGIN_ID_MAX - 1}}}$")

#: 없는 아이디로 로그인을 시도했을 때 대조할 가짜 해시. 무작위 값으로 미리 만들어 둔
#: 것이라 어떤 비밀번호와도 맞지 않는다. 존재 여부가 응답 시간으로 새는 걸 막는 용도다.
_DUMMY_HASH = "$2b$10$oMtSZRFYjonOJ//KrxSnhOZaa0s5EkL6Aq0O1qV8gGMgSSAQSnuQK"

#: 너무 뻔해서 남이 그냥 맞히는 비밀번호. 아이디와 같은 값도 여기서 함께 막는다.
_WEAK_PASSWORDS = frozenset(
    {
        "password",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "abc12345",
        "11111111",
        "00000000",
        "iloveyou",
        "bulletbrak",
    }
)


def issue_token() -> str:
    """새 디바이스 토큰(평문). 이 값은 발급 응답에서 딱 한 번만 나간다."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_code() -> str:
    """새 인계 코드(평문, 하이픈 포함). 발급 응답에서 딱 한 번만 나간다."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return format_code(raw)


def format_code(raw: str) -> str:
    """`K7M29QPX3W5B` -> `K7M2-9QPX-3W5B`. 화면에 보여줄 때만 쓴다."""
    return "-".join(raw[i : i + CODE_GROUP] for i in range(0, len(raw), CODE_GROUP))


def normalize_code(value: str | None) -> str | None:
    """사용자가 입력한 코드를 정규형(하이픈 없는 대문자 12자)으로 바꾼다.

    하이픈/공백은 버리고, 소문자는 올리고, 헷갈리는 글자(O·I·L)는 되돌린다.
    길이나 글자가 어긋나면 None — **DB 를 만지기 전에 여기서 걸러진다**
    (형식만으로 아웃인 값에까지 조회 비용을 쓸 이유가 없다).
    """
    if not value:
        return None
    cleaned = "".join(ch for ch in value.upper() if ch.isalnum()).translate(_CODE_CONFUSABLES)
    if len(cleaned) != CODE_LENGTH:
        return None
    if any(ch not in CODE_ALPHABET for ch in cleaned):
        return None
    return cleaned


def hash_code(value: str) -> str:
    """정규형 코드의 해시. 저장·조회 모두 이 값만 쓴다."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
# 로그인 (사용자가 직접 정하는 아이디 / 비밀번호)
# --------------------------------------------------------------------------


def normalize_login_id(value: str | None) -> str | None:
    """입력한 아이디를 정규형(소문자)으로. 규칙에 안 맞으면 None.

    대소문자를 구분하지 않는다 — `MinSu` 로 만들고 `minsu` 로 로그인하려다 막히는 건
    사용자 입장에서 그냥 버그다. 저장도 조회도 소문자 한 벌만 쓴다.
    """
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned if _LOGIN_ID_RE.match(cleaned) else None


def password_problem(password: str, login_id: str | None = None) -> str | None:
    """비밀번호가 규칙에 걸리면 사용자에게 보여줄 문장을, 괜찮으면 None 을 준다.

    규칙을 여기 한 곳에만 두는 이유는 프런트와 어긋나지 않게 하기 위해서다 —
    화면의 안내 문구도 이 함수가 돌려준 문장을 그대로 쓴다.
    """
    if len(password) < passwords.MIN_PASSWORD_LENGTH:
        return f"비밀번호는 {passwords.MIN_PASSWORD_LENGTH}자 이상이어야 합니다."
    if len(password) > passwords.MAX_PASSWORD_LENGTH:
        return f"비밀번호는 {passwords.MAX_PASSWORD_LENGTH}자를 넘을 수 없습니다."
    lowered = password.lower()
    if lowered in _WEAK_PASSWORDS:
        return "너무 흔한 비밀번호입니다. 다른 것으로 정해 주세요."
    if login_id and lowered == login_id.lower():
        return "아이디와 같은 비밀번호는 쓸 수 없습니다."
    if len(set(password)) == 1:
        return "같은 글자만으로는 만들 수 없습니다."
    return None


async def set_credentials(
    session: AsyncSession, account: Account, login_id: str, password: str
) -> tuple[bool, str, str]:
    """계정에 아이디/비밀번호를 붙이거나 바꾼다.

    이미 아이디가 있는 계정이 다른 아이디를 보내면 아이디까지 바뀐다(옮겨 타기가
    아니라 이름 바꾸기다 — 계정 자체는 그대로다).

    Returns:
        (성공 여부, 사유 코드, 사용자에게 보여줄 문장)
    """
    normalized = normalize_login_id(login_id)
    if normalized is None:
        return (
            False,
            "invalid_id",
            f"아이디는 영문 소문자로 시작하는 {LOGIN_ID_MIN}~{LOGIN_ID_MAX}자"
            " (영문 소문자·숫자·밑줄)여야 합니다.",
        )

    problem = password_problem(password, normalized)
    if problem is not None:
        return False, "weak_password", problem

    # 남이 쓰고 있는 아이디인가. 내 계정이 이미 그 아이디면(비번만 바꾸는 경우) 통과다.
    owner = await session.scalar(select(Account.id).where(Account.login_id == normalized))
    if owner is not None and owner != account.id:
        return False, "taken", "이미 사용 중인 아이디입니다."

    account.login_id = normalized
    account.password_hash = await passwords.hash_password(password)
    account.last_seen_at = _utcnow()
    await session.flush()
    return True, "ok", "아이디와 비밀번호를 저장했어요."


async def login(
    session: AsyncSession, login_id: str, password: str, *, label: str = ""
) -> tuple[Account, str] | None:
    """아이디/비밀번호 -> (계정, 새 디바이스 토큰). 어느 쪽이 틀려도 None.

    아이디가 없을 때도 **해싱을 한 번 돌린다.** 없는 아이디만 빨리 실패하면 응답
    시간만 재도 "이 아이디는 존재한다"를 알아낼 수 있기 때문이다.
    """
    normalized = normalize_login_id(login_id)
    account = (
        await session.scalar(select(Account).where(Account.login_id == normalized))
        if normalized is not None
        else None
    )

    # 계정이 없으면 더미 해시로 대조한다 — 어느 쪽이든 정확히 한 번 해싱하므로
    # 응답 시간에서 아이디 존재 여부가 새지 않는다.
    hashed = (account.password_hash if account else None) or _DUMMY_HASH
    ok = await passwords.verify_password(password, hashed)
    if account is None or not ok:
        return None

    token = await issue_additional_token(session, account, label=label)
    account.last_seen_at = _utcnow()
    return account, token


# --------------------------------------------------------------------------
# 인계 코드 (다른 기기 로그인)
# --------------------------------------------------------------------------


async def issue_recovery_code(session: AsyncSession, account: Account) -> str:
    """계정 인계 코드를 새로 발급하고 평문을 돌려준다.

    **이미 코드가 있으면 그 코드는 이 호출로 죽는다**(계정당 하나). 재발급이 곧
    "유출됐을 때의 폐기 수단"이기 때문에 덮어쓰기가 기능이지 부작용이 아니다.

    평문은 저장하지 않으므로 여기서 돌려준 값을 놓치면 다시 볼 방법이 없다.
    """
    # 60비트라 현실적으로 부딪히지 않지만, UNIQUE 제약이 있으니 만에 하나를 위해 몇 번 돌린다.
    for _ in range(5):
        code = issue_code()
        digest = hash_code(normalize_code(code) or "")
        taken = await session.scalar(
            select(Account.id).where(Account.recovery_code_hash == digest)
        )
        if taken is None:
            account.recovery_code_hash = digest
            account.recovery_code_issued_at = _utcnow()
            account.last_seen_at = _utcnow()
            await session.flush()
            return code
    raise RuntimeError("인계 코드를 발급할 수 없습니다.")


async def redeem_recovery_code(
    session: AsyncSession, code: str | None, *, label: str = ""
) -> tuple[Account, str] | None:
    """인계 코드 -> (계정, 새 디바이스 토큰). 모르는 코드면 None.

    코드는 **소모되지 않는다** — 기기를 셋, 넷 붙일 수 있어야 하기 때문이다.
    대신 발급 계정에 토큰이 하나 더 생기고, 그 토큰이 이 기기의 신원이 된다.
    """
    normalized = normalize_code(code)
    if normalized is None:
        return None

    account = await session.scalar(
        select(Account).where(Account.recovery_code_hash == hash_code(normalized))
    )
    if account is None:
        return None

    token = await issue_additional_token(session, account, label=label)
    account.last_seen_at = _utcnow()
    return account, token


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
