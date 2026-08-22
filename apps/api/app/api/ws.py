"""WebSocket 엔드포인트 `/ws/{code}` (PROTOCOL §2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.ws_join import create_player, load_identity, ranked_denial
from app.game import constants as C
from app.game import engine
from app.game.bullets import fire, fire_strong
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
    RematchMsg,
    SetMapMsg,
    SetPlatformsMsg,
    parse_client_message,
)
from app.services import chat as chat_service
from app.services import results
from app.services.hub import hub

logger = logging.getLogger(__name__)
router = APIRouter()

CLOSE_BAD_REQUEST = 4400
#: 경쟁전 방인데 계정이 없다. 기록할 곳이 없는 사람에게 랭크를 걸 수는 없다.
CLOSE_NEEDS_ACCOUNT = 4401
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

        # 신원 조회는 입장 시 딱 한 번이다(틱 루프가 아니라 여기서만 DB 를 만진다).
        identity = await load_identity(join.token)

        denied = ranked_denial(room, identity)
        if denied is not None:
            await _fail(ws, denied, CLOSE_NEEDS_ACCOUNT)
            return

        player = create_player(room, join, nickname, identity)
        room.players[player.id] = player
        room.scores.setdefault(player.id, 0)
        room.round_wins.setdefault(player.id, 0)
        player_id = player.id

        hub.add(code, player.id, ws)
        await hub.send(
            ws,
            {
                "type": "welcome",
                "player_id": player.id,
                # 계정에 연결됐는지 클라이언트가 알 수 있게 알려준다(없으면 null).
                "account_id": player.account_id,
                "room": room_state(room),
            },
        )
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


def _is_host(room: Room, player: Player) -> bool:
    """방장 = 가장 먼저 입장한 사람. 클라이언트 RoomScreen 의 판정과 같은 규칙이다."""
    first = next(iter(room.players), None)
    return first is None or first == player.id


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

    elif msg_type == "open_cards":
        # 훈련장 전용. 대전 방에서 오면 engine 이 조용히 무시한다.
        engine.open_training_cards(room)

    elif msg_type == "chat" and isinstance(payload, ChatMsg):
        message = chat_service.push(room, player.nickname, payload.text)
        if message:
            await hub.broadcast(room.code, message)

    elif msg_type == "set_map" and isinstance(payload, SetMapMsg):
        # 맵은 방장(가장 먼저 들어온 사람)만 바꾼다.
        if _is_host(room, player) and engine.set_map(room, payload.map_id):
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "set_platforms" and isinstance(payload, SetPlatformsMsg):
        # 맵 에디터도 방장 전용.
        if _is_host(room, player) and engine.set_platforms(room, payload.platforms):
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "reset_platforms":
        if _is_host(room, player) and engine.clear_platforms(room):
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "start_game":
        if engine.start_game(room):
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "restart":
        if room.phase == "finished":
            engine.reset_match(room)
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})

    elif msg_type == "rematch" and isinstance(payload, RematchMsg):
        await _do_rematch(room, player, payload.accept)

    elif msg_type == "avatar" and isinstance(payload, AvatarMsg):
        if room.phase in ("waiting", "finished"):
            custom = payload.customization.model_dump()
            custom["color"] = player.customization.get("color", custom.get("color"))
            player.customization = custom
            await hub.broadcast(room.code, {"type": "room_state", "room": room_state(room)})


async def _do_rematch(room: Room, player: Player, accept: bool) -> None:
    """리매치 투표. 상대가 아직이면 스냅샷의 rematch 로만 알리고, 결론이 나면 방송한다."""
    result = engine.vote_rematch(room, player.id, accept)
    if result in ("ignored", "pending"):
        return

    note = "리매치!" if result == "start" else "리매치를 거절했습니다."
    message = chat_service.push(room, player.nickname, note)
    if message:
        await hub.broadcast(room.code, message)
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
    left = room.players.pop(player_id, None)
    # 경쟁전 도중 이탈은 패배로 기록한다 — 아니면 "질 것 같으면 나간다"가 최적 전략이 된다.
    # room.scores 를 지우기 **전에** 결과를 복사해 둬야 나간 사람의 점수가 남는다.
    if (
        room.ranked
        and left is not None
        and room.phase in ("playing", "round_over", "picking")
        and len(room.players) == 1
    ):
        results.schedule(results.capture_forfeit(room, left))
    room.scores.pop(player_id, None)
    room.round_wins.pop(player_id, None)
    room.rematch_votes.discard(player_id)
    if room.loser_to_pick == player_id:
        room.loser_to_pick = None
        engine.reset_round(room)

    if not room.players:
        hub.drop_room(code)
        room_manager.remove(code)
        return

    if room.mode == "pvp" and len(room.players) < 2 and room.phase != "waiting":
        engine.reset_match(room)

    # 남은 사람에게 "누가 나갔는지"를 먼저 알린다. room_state 가 화면을 대기실로 되돌리기
    # 때문에, 순서가 뒤집히면 알림이 화면 전환에 묻힌다.
    await hub.broadcast(
        code,
        {
            "type": "player_left",
            "player_id": player_id,
            "nickname": (left.nickname if left else "") or "익명",
            "players_left": len(room.players),
        },
    )
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
