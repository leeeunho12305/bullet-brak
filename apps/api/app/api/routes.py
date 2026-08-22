"""REST API (PROTOCOL §1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import db_ready
from app.game import maps
from app.game.cards import card_infos
from app.game.rooms import RoomError, room_manager
from app.schemas.messages import (
    CreateRoomRequest,
    CreateRoomResponse,
    HealthResponse,
    RoomInfoResponse,
)

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """DB 상태와 무관하게 항상 200 이다.

    Render 의 healthCheckPath 와 compose healthcheck 가 이 엔드포인트를 본다.
    DB 가 없어도 게임은 정상이므로 여기서 실패를 내면 배포가 통째로 막힌다.
    프런트는 `db` 필드로 계정 기능을 켤지 판단한다.
    """
    return HealthResponse(status="ok", db="on" if db_ready() else "off")


@router.post("/rooms", response_model=CreateRoomResponse, status_code=201)
async def create_room(body: CreateRoomRequest) -> CreateRoomResponse:
    """방 생성. 경쟁전은 DB 가 있어야 만들 수 있다.

    랭크는 기록이 남아야 뜻이 있다. DB 가 없는 배포에서 경쟁전 방을 열어 주면 판은
    돌아가는데 아무것도 안 남아서, 플레이어 입장에서는 그냥 고장 난 기능이 된다.
    """
    if body.ranked and not db_ready():
        raise HTTPException(status_code=503, detail="이 서버에서는 경쟁전을 할 수 없습니다.")
    try:
        room = room_manager.create(
            mode=body.mode,
            max_players=body.max_players,
            map_id=body.map_id,
            ranked=body.ranked,
        )
    except RoomError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CreateRoomResponse(
        code=room.code,
        mode=room.mode,
        max_players=room.max_players,
        map_id=room.map_id,
        ranked=room.ranked,
    )


@router.get("/rooms/{code}", response_model=RoomInfoResponse)
async def get_room(code: str) -> RoomInfoResponse:
    room = room_manager.get(code)
    if room is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 방입니다.")
    return RoomInfoResponse(
        code=room.code,
        mode=room.mode,
        max_players=room.max_players,
        player_count=len(room.players),
        phase=room.phase,
        map_id=room.map_id,
        ranked=room.ranked,
    )


@router.get("/cards")
async def get_cards() -> list[dict[str, Any]]:
    return card_infos()


@router.get("/maps")
async def get_maps() -> list[dict[str, Any]]:
    """맵 카탈로그(발판·스폰·테마 포함). 대기실 맵 선택기가 미리보기에 그대로 쓴다."""
    return maps.catalog()
