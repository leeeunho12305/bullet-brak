"""WS 입장 처리 — 신원 조회 / 경쟁전 자격 / 플레이어 생성.

`ws.py` 에서 떼어낸 조각이다(파일당 400줄). 여기 있는 것은 전부 **입장 시 딱 한 번**
도는 코드라 DB 를 만져도 된다 — 틱 루프가 아니다.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from typing import Any

from app.db import db_ready, session_scope
from app.game import constants as C
from app.game import engine
from app.game.cards import reset_card_state
from app.game.models import Player, Room
from app.schemas.messages import JoinMsg
from app.services import accounts as account_service
from app.services import matches as match_service
from app.services import seasons as season_service

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Identity:
    """계정에서 떼어낸 값 사본.

    ORM 객체를 세션 밖으로 들고 나가면 lazy load 가 터진다. 필요한 필드만 복사한다.
    """

    account_id: str
    nickname: str
    customization: dict[str, Any]
    coins: int
    #: 지금 시즌의 티어(1~25) / RR. 배치 전이거나 경쟁전을 안 했으면 0 이다.
    tier: int = 0
    rr: int = 0


async def load_identity(token: str | None) -> Identity | None:
    """디바이스 토큰 -> 계정. DB 가 꺼져 있거나 토큰이 없으면 None(= 비로그인 입장).

    DB 오류로 입장이 막히면 안 되므로 예외는 삼키고 비로그인으로 떨어뜨린다.
    """
    if not token or not db_ready():
        return None
    try:
        async with session_scope() as session:
            account = await account_service.resolve_token(session, token)
            if account is None:
                return None

            # 이름표에 붙일 티어. 시즌이 아직 없거나 경쟁전을 한 번도 안 했으면 0 이다
            # (여기서 시즌을 새로 열지는 않는다 — 그건 결과를 기록할 때의 일이다).
            season = await season_service.current_season(session)
            profile = (
                await match_service.get_profile(session, account.id, season.id)
                if season is not None
                else None
            )

            return Identity(
                account_id=account.id,
                nickname=account.nickname,
                customization=dict(account.customization or {}),
                coins=account.coins,
                tier=profile.tier if profile else 0,
                rr=profile.rr if profile else 0,
            )
    except Exception:
        logger.exception("계정 조회 실패 — 비로그인으로 입장시킨다.")
        return None


def ranked_denial(room: Room, identity: Identity | None) -> str | None:
    """경쟁전 방에 못 들어가는 이유(들어가도 되면 None).

    두 가지를 막는다.

    1. **비로그인 입장** — 랭크는 기록이 남아야 뜻이 있는데 계정이 없으면 남길 곳이 없다.
       DB 가 꺼진 배포에서는 애초에 경쟁전 방을 만들 수 없으므로 여기 걸리는 건
       "이 브라우저에 계정이 안 붙은" 경우다.
    2. **같은 계정 두 번** — 탭 두 개로 자기 자신과 붙으면 RR 을 원하는 대로 옮길 수 있다.
    """
    if not room.ranked:
        return None
    if identity is None:
        return "경쟁전은 로그인한 계정만 입장할 수 있습니다."
    if any(p.account_id == identity.account_id for p in room.players.values()):
        return "같은 계정으로는 경쟁전 방에 두 번 들어올 수 없습니다."
    return None


def create_player(
    room: Room, join: JoinMsg, query_nickname: str, identity: Identity | None = None
) -> Player:
    nick = join.nickname
    if nick == "익명":
        # 쿼리스트링 -> 계정 닉네임 순으로 되짚는다. 아바타 편집기는 클라이언트에
        # 있고 변경 시 PATCH /api/me 로 올라가므로, 명시적으로 보낸 값이 우선이다.
        nick = (query_nickname or "").strip()[:16] or (identity.nickname if identity else "") or "익명"

    custom = join.customization.model_dump()
    custom["color"] = _pick_color(room, custom.get("color"))

    x, y = engine.random_spawn(room)
    player = Player(
        id=uuid.uuid4().hex[:8],
        nickname=nick,
        customization=custom,
        # 로그인 상태면 코인은 계정 잔액이다. join.coins(클라이언트 신고값)는 버린다.
        coins=identity.coins if identity else join.coins,
        account_id=identity.account_id if identity else None,
        tier=identity.tier if identity else 0,
        rr=identity.rr if identity else 0,
        x=x,
        y=y,
    )
    try:
        reset_card_state(player)
    except Exception:
        logger.exception("reset_card_state 실패")
    return player


def _pick_color(room: Room, requested: str | None) -> str:
    """방 안에서 겹치지 않는 색. 요청한 색이 이미 쓰이면 남은 것 중 하나를 준다."""
    taken = {str(p.customization.get("color")) for p in room.players.values()}
    if requested and requested not in taken:
        return requested
    available = [c for c in C.AVATAR_PALETTE if c not in taken]
    return random.choice(available) if available else C.AVATAR_PALETTE[0]
