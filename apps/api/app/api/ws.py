"""WebSocket 엔드포인트 `/ws/{code}` (PROTOCOL §2)."""

from __future__ import annotations

import json
import logging
import random
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.game import constants as C
from app.game import engine
from app.game.bullets import fire, fire_strong
from app.game.cards import reset_card_state
from app.game.models import Player, Room
from app.game.rooms import room_manager
from app.game.serialize import room_state
from app.schemas.messages import (
    AimMsg,
    AvatarMsg,
    ChatMsg,
    InputMsg,
    JoinMsg,
    PickCardMsg,
    parse_client_message,
)
from app.services import chat as chat_service
from app.services.hub import hub

logger = logging.getLogger(__name__)
router = APIRouter()

CLOSE_BAD_REQUEST = 4400
CLOSE_NOT_FOUND = 4404
CLOSE_FULL = 4409


@router.websocket("/ws/{code}")
async def game_ws(ws: WebSocket, code: str, nickname: str = Query(default="익명")) -> None:
    await ws.accept()
    player_id: str | None = None
    try:
        join = await _await_join(ws)
        if join is None:
            return

        room = room_manager.get(code)
        if room is None:
            await _fail(ws, "존재하지 않는 방입니다.", CLOSE_NOT_FOUND)
            return
        if room_manager.is_full(room):
            await _fail(ws, "방이 가득 찼습니다.", CLOSE_FULL)
            return

        player = _create_player(room, join, nickname)
        room.players[player.id] = player
        room.scores.setdefault(player.id, 0)
        room.round_wins.setdefault(player.id, 0)
        player_id = player.id

        hub.add(code, player.id, ws)
        await hub.send(ws, {"type": "welcome", "player_id": player.id, "room": room_state(room)})
        await hub.broadcast(code, {"type": "room_state", "room": room_state(room)})

        await _message_loop(ws, room, player)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws 처리 중 예외 (code=%s)", code)
    finally:
        await _cleanup(code, player_id)


# --------------------------------------------------------------------------
# 입장
# --------------------------------------------------------------------------


async def _await_join(ws: WebSocket) -> JoinMsg | None:
    raw = await _receive_json(ws)
    parsed = parse_client_message(raw) if raw is not None else None
    if parsed is None or parsed[0] != "join":
        await _fail(ws, "첫 메시지는 join 이어야 합니다.", CLOSE_BAD_REQUEST)
        return None
    payload = parsed[1]
    return payload if isinstance(payload, JoinMsg) else None


def _create_player(room: Room, join: JoinMsg, query_nickname: str) -> Player:
    nick = join.nickname
    if nick == "익명":
        nick = (query_nickname or "").strip()[:16] or "익명"

    custom = join.customization.model_dump()
    custom["color"] = _pick_color(room, custom.get("color"))

    x, y = engine.random_spawn()
    player = Player(
        id=uuid.uuid4().hex[:8],
        nickname=nick,
        customization=custom,
        coins=join.coins,
        x=x,
        y=y,
    )
    try:
        reset_card_state(player)
    except Exception:
        logger.exception("reset_card_state 실패")
    return player


def _pick_color(room: Room, requested: str | None) -> str:
    taken = {str(p.customization.get("color")) for p in room.players.values()}
    if requested and requested not in taken:
        return requested
    available = [c for c in C.AVATAR_PALETTE if c not in taken]
    return random.choice(available) if available else C.AVATAR_PALETTE[0]


# --------------------------------------------------------------------------
# 메시지 루프
# --------------------------------------------------------------------------


async def _message_loop(ws: WebSocket, room: Room, player: Player) -> None:
    while True:
        raw = await _receive_json(ws)
        if raw is None:
            continue
        parsed = parse_client_message(raw)
        if parsed is None:
            continue
        msg_type, payload = parsed
        try:
            await _handle(room, player, msg_type, payload)
        except Exception:
            logger.exception("메시지 처리 실패 type=%s", msg_type)


async def _handle(room: Room, player: Player, msg_type: str, payload: Any) -> None:
    if msg_type == "input" and isinstance(payload, InputMsg):
        inp = player.inputs
        inp.left, inp.right, inp.block = payload.left, payload.right, payload.block
        if not payload.jump:
            inp.jump_consumed = False
        inp.jump = payload.jump

    elif msg_type == "aim" and isinstance(payload, AimMsg):
        player.aim.x, player.aim.y = payload.x, payload.y

    elif msg_type == "shoot":
        _do_shoot(room, player)

    elif msg_type == "strong_start":
        if player.alive and player.cooldown <= 0 and player.silence_timer <= 0:
            player.charging = True
            player.charge = 0.0

    elif msg_type == "strong_release":
        _do_strong_release(room, player)

    elif msg_type == "pick_card" and isinstance(payload, PickCardMsg):
        engine.pick_card(room, player.id, payload.card_id)

    elif msg_type == "chat" and isinstance(payload, ChatMsg):
        message = chat_service.push(room, player.nickname, payload.text)
        if message:
            await hub.broadcast(room.code, message)

    elif msg_type == "start_game":
        if engine.start_game(room):
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "restart":
        if room.phase == "finished":
            engine.reset_match(room)
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "avatar" and isinstance(payload, AvatarMsg):
        if room.phase in ("waiting", "finished"):
            custom = payload.customization.model_dump()
            custom["color"] = player.customization.get("color", custom.get("color"))
            player.customization = custom
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})


def _do_shoot(room: Room, player: Player) -> None:
    if room.phase != "playing" or not player.alive:
        return
    if player.cooldown > 0 or player.silence_timer > 0:
        return
    try:
        fire(room, player)
    except Exception:
        logger.exception("fire 실패")
        return
    # 레거시가 빠뜨린 쿨다운 적용
    player.cooldown = player.max_cooldown


def _do_strong_release(room: Room, player: Player) -> None:
    if not player.charging:
        return
    # 차징량(player.charge)은 게임코어가 읽으므로 발사 후에 초기화한다
    fired = False
    if room.phase == "playing" and player.alive and player.silence_timer <= 0:
        try:
            fire_strong(room, player)
            fired = True
        except Exception:
            logger.exception("fire_strong 실패")
    player.charging = False
    player.charge = 0.0
    if fired:
        player.cooldown = max(player.cooldown, C.STRONG_COOLDOWN)


# --------------------------------------------------------------------------
# 종료 처리
# --------------------------------------------------------------------------


async def _cleanup(code: str, player_id: str | None) -> None:
    if player_id is None:
        return
    hub.remove(code, player_id)
    room = room_manager.get(code)
    if room is None:
        return
    room.players.pop(player_id, None)
    room.scores.pop(player_id, None)
    room.round_wins.pop(player_id, None)
    if room.loser_to_pick == player_id:
        room.loser_to_pick = None
        engine.reset_round(room)

    if not room.players:
        hub.drop_room(code)
        room_manager.remove(code)
        return

    if room.mode == "pvp" and len(room.players) < 2 and room.phase != "waiting":
        engine.reset_match(room)
    await hub.broadcast(code, {"type": "room_state", "room": room_state(room)})


# --------------------------------------------------------------------------
# 유틸
# --------------------------------------------------------------------------


async def _receive_json(ws: WebSocket) -> dict[str, Any] | None:
    text = await ws.receive_text()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def _fail(ws: WebSocket, message: str, close_code: int) -> None:
    await hub.send(ws, {"type": "error", "message": message})
    try:
        await ws.close(code=close_code)
    except Exception:
        pass
