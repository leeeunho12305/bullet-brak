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
from app.schemas.messages import (
    AccountResponse,
    CreateAnonAccountRequest,
    CreateAnonAccountResponse,
    UpdateProfileRequest,
)
from app.services import accounts as account_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["accounts"])

DB_OFF_DETAIL = "계정 기능이 비활성 상태입니다(DB 미설정)."


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
