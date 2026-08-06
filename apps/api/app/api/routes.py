"""REST API (PROTOCOL §1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

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
    return HealthResponse(status="ok")


@router.post("/rooms", response_model=CreateRoomResponse, status_code=201)
async def create_room(body: CreateRoomRequest) -> CreateRoomResponse:
    try:
        room = room_manager.create(
            mode=body.mode, max_players=body.max_players, map_id=body.map_id
        )
    except RoomError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CreateRoomResponse(
        code=room.code,
        mode=room.mode,
        max_players=room.max_players,
        map_id=room.map_id,
    )


@router.get("/rooms/{code}", response_model=RoomInfoResponse)
async def get_room(code: str) -> RoomInfoResponse:
    room = room_manager.get(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    return RoomInfoResponse(
        code=room.code,
        mode=room.mode,
        max_players=room.max_players,
        player_count=len(room.players),
        phase=room.phase,
        map_id=room.map_id,
    )


@router.get("/cards")
async def get_cards() -> list[dict[str, Any]]:
    return card_infos()


@router.get("/maps")
async def get_maps() -> list[dict[str, Any]]:
    """맵 카탈로그(발판·스폰·테마 포함). 대기실 맵 선택기가 미리보기에 그대로 쓴다."""
    return maps.catalog()
