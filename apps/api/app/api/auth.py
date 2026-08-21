"""계정 REST — `/api/auth/*`, `/api/me`.

DB 가 꺼져 있으면(`DATABASE_URL` 없음) 전부 503 을 돌려준다. 프런트는 그 경우
예전처럼 localStorage 만 쓰는 모드로 동작한다 — 그래서 503 이 에러 화면이 되면 안 된다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import db_ready, session_scope
from app.db.models import Account, AccountItem
from app.game import shop
from app.schemas.messages import (
    AccountResponse,
    AuthResultResponse,
    BuyItemRequest,
    BuyItemResponse,
    CreateAnonAccountRequest,
    CreateAnonAccountResponse,
    LoginRequest,
    RecoveryCodeResponse,
    RedeemCodeRequest,
    SetCredentialsRequest,
    SetCredentialsResponse,
    UpdateProfileRequest,
)
from app.services import accounts as account_service
from app.services.ratelimit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["accounts"])

DB_OFF_DETAIL = "계정 기능이 비활성 상태입니다(DB 미설정)."

#: 로그인/인계 코드 시도 제한. 맞히면 계정이 통째로 넘어가는 창구라 여기만 조인다.
#: 10분에 10번이면 사람이 오타를 내는 속도로는 절대 안 걸리고, 자동 대입에는 벽이 된다.
login_limiter = RateLimiter(limit=10, window_sec=600.0)


def _client_key(request: Request) -> str:
    """레이트리밋 키. 프록시 뒤(nginx/Render)에서는 X-Forwarded-For 의 첫 항목이 진짜다."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _guard_attempt(request: Request) -> None:
    """시도를 한 번 기록하고, 한도를 넘겼으면 429 로 끊는다."""
    key = _client_key(request)
    if not login_limiter.hit(key):
        raise HTTPException(
            status_code=429,
            detail="시도가 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(login_limiter.retry_after(key))},
        )


async def db_session() -> AsyncIterator[AsyncSession]:
    """세션 의존성. DB 가 꺼져 있으면 500 이 아니라 503 으로 알린다.

    (프런트가 503 을 "계정 기능 없음"으로 읽고 로컬 모드로 내려간다.)
    """
    if not db_ready():
        raise HTTPException(status_code=503, detail=DB_OFF_DETAIL)
    async with session_scope() as session:
        yield session


def _bearer(authorization: str | None) -> str | None:
    """`Authorization: Bearer <token>` 에서 토큰만 뽑는다."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


async def current_account(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(db_session),
) -> Account:
    """인증 의존성. 토큰이 없거나 모르는 값이면 401."""
    account = await account_service.resolve_token(session, _bearer(authorization))
    if account is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return account


async def _to_response(session: AsyncSession, account: Account) -> AccountResponse:
    owned = await account_service.owned_keys(session, account.id)
    return AccountResponse(
        id=account.id,
        nickname=account.nickname,
        customization=account.customization or {},
        coins=account.coins,
        level=account.level,
        xp=account.xp,
        matches_played=account.matches_played,
        matches_won=account.matches_won,
        owned_items=sorted(owned),
        login_id=account.login_id,
        # 있다/없다만 알린다. 평문 코드는 발급 응답에서만 나가고 다시는 나가지 않는다.
        has_recovery_code=account.recovery_code_hash is not None,
    )


@router.post("/auth/anon", response_model=CreateAnonAccountResponse, status_code=201)
async def create_anon_account(
    body: CreateAnonAccountRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> CreateAnonAccountResponse:
    """익명 계정 발급. 브라우저가 토큰을 아직 안 갖고 있을 때 딱 한 번 부른다.

    localStorage 에 있던 프로필(닉네임/아바타/코인/보유 아이템)을 그대로 물려받는다.
    코인은 `ACCOUNT_SEED_COINS_MAX` 로 잘린다 — 위조 가능한 값이라 무제한으로 받지 않는다.
    """
    settings = get_settings()

    account, token = await account_service.create_anonymous(
        session,
        nickname=body.nickname,
        customization=body.customization.model_dump(),
        seed_coins=min(body.seed_coins, settings.account_seed_coins_max),
        label=(request.headers.get("user-agent") or "")[:64],
    )

    # 기존 보유 아이템 이관. 최초 계정 생성 시점에만 통과하는 창구다.
    for key in dict.fromkeys(body.seed_items):
        clean = (key or "").strip()[:48]
        if clean:
            session.add(AccountItem(account_id=account.id, item_key=clean, paid=0))
    await session.flush()

    return CreateAnonAccountResponse(
        token=token,
        account=await _to_response(session, account),
    )


@router.post("/auth/login", response_model=AuthResultResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> AuthResultResponse:
    """아이디/비밀번호 로그인. 성공하면 **이 기기의 디바이스 토큰**이 새로 발급된다.

    기존 토큰을 회수하지 않는다 — 기기 여러 대에서 동시에 로그인해 있는 게 정상이다.
    클라이언트는 받은 토큰을 localStorage 에 덮어쓰기만 하면 된다.

    틀린 비밀번호는 장애가 아니므로 200 + ok=false 다. 다만 시도가 잦으면 429 로 끊는다.
    """
    _guard_attempt(request)

    result = await account_service.login(
        session,
        body.login_id,
        body.password,
        label=(request.headers.get("user-agent") or "")[:64],
    )
    if result is None:
        return AuthResultResponse(ok=False, reason="invalid_credentials")

    account, token = result
    return AuthResultResponse(
        ok=True, reason="ok", token=token, account=await _to_response(session, account)
    )


@router.post("/auth/redeem", response_model=AuthResultResponse)
async def redeem_code(
    body: RedeemCodeRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> AuthResultResponse:
    """인계 코드로 로그인. 비밀번호를 잊었을 때의 우회로다.

    코드는 소모되지 않는다 — 기기를 셋, 넷 붙일 수 있어야 하기 때문이다.
    유출됐다고 판단되면 `POST /api/me/recovery-code` 로 재발급해 옛 코드를 죽인다.
    """
    _guard_attempt(request)

    result = await account_service.redeem_recovery_code(
        session,
        body.code,
        label=(request.headers.get("user-agent") or "")[:64],
    )
    if result is None:
        return AuthResultResponse(ok=False, reason="invalid_code")

    account, token = result
    return AuthResultResponse(
        ok=True, reason="ok", token=token, account=await _to_response(session, account)
    )


@router.post("/me/credentials", response_model=SetCredentialsResponse)
async def set_credentials(
    body: SetCredentialsRequest,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> SetCredentialsResponse:
    """지금 계정에 아이디/비밀번호를 붙인다(이미 있으면 변경).

    **새 계정을 만드는 게 아니라 지금 쓰던 익명 계정을 승격시킨다** — 그래서 코인과
    아이템이 그대로 따라온다. 회원가입 화면이 따로 없는 이유이기도 하다.
    """
    ok, reason, message = await account_service.set_credentials(
        session, account, body.login_id, body.password
    )
    return SetCredentialsResponse(
        ok=ok,
        reason=reason,
        login_id=account.login_id if ok else None,
        message=message,
    )


@router.post("/me/recovery-code", response_model=RecoveryCodeResponse, status_code=201)
async def issue_recovery_code(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> RecoveryCodeResponse:
    """인계 코드를 새로 발급한다. **이미 있던 코드는 이 호출로 무효가 된다.**

    평문은 이 응답에서만 나온다(서버는 해시만 갖는다). 화면에 한 번 보여 주고
    사용자가 어딘가 적어 두게 하는 것이 이 코드의 사용법이다.
    """
    code = await account_service.issue_recovery_code(session, account)
    return RecoveryCodeResponse(code=code, issued_at=account.recovery_code_issued_at)


@router.get("/me", response_model=AccountResponse)
async def get_me(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> AccountResponse:
    return await _to_response(session, account)


@router.patch("/me", response_model=AccountResponse)
async def patch_me(
    body: UpdateProfileRequest,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> AccountResponse:
    """닉네임/아바타만 바꾼다. 코인은 클라이언트가 정할 수 없다."""
    await account_service.update_profile(
        session,
        account,
        nickname=body.nickname,
        customization=(body.customization.model_dump() if body.customization else None),
    )
    return await _to_response(session, account)


@router.post("/me/items", response_model=BuyItemResponse)
async def buy_item(
    body: BuyItemRequest,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(db_session),
) -> BuyItemResponse:
    """파츠 구매. **가격은 서버 가격표에서만 나온다**(요청 본문에 price 가 와도 무시).

    실패해도 HTTP 200 + `ok=false` 다 — 코인 부족은 장애가 아니라 정상적인 결과고,
    프런트는 어느 쪽이든 응답의 coins/owned_items 로 상태를 맞추면 된다.
    (인증 실패 401, DB 없음 503 만 예외다.)

    0등급(가격 0) 파츠는 원래 전부에게 열려 있는 기본 파츠라 결제가 아니라 그냥
    소유 기록만 남는다 — 차감이 0 이라 중복 호출해도 새는 코인이 없다.
    """
    key = body.item_key.strip()
    price = shop.price_of(key)

    if price is None:
        # 모르는 카테고리(예: 항상 무료인 colors) / 범위 밖 인덱스 / 형식 오류.
        ok, reason = False, "invalid_item"
    else:
        ok, reason = await account_service.buy_item(session, account, key, price)

    owned = await account_service.owned_keys(session, account.id)
    return BuyItemResponse(
        ok=ok,
        reason=reason,
        coins=account.coins,
        owned_items=sorted(owned),
    )
