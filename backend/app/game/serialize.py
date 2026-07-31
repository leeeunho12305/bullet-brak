"""스냅샷 직렬화. PROTOCOL §3 의 키 이름/구조를 그대로 만든다.

dataclass 를 통째로 dump 하지 않는다(내부 flags/타이머 유출 금지).
"""

from __future__ import annotations

from typing import Any

from app.game.cards import card_info
from app.game.models import Bot, Bullet, Player, Room, Zone


def _customization(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "eye": int(raw.get("eye", 0)),
        "mouth": int(raw.get("mouth", 0)),
        "detail": int(raw.get("detail", 0)),
        "color": str(raw.get("color", "#ff6b6b")),
    }


def player_snap(room: Room, p: Player) -> dict[str, Any]:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "customization": _customization(p.customization),
        "x": p.x,
        "y": p.y,
        "width": p.width,
        "height": p.height,
        "vx": p.vx,
        "vy": p.vy,
        "hp": p.hp,
        "max_hp": p.max_hp,
        "alive": p.alive,
        "aim": {"x": p.aim.x, "y": p.aim.y},
        "cooldown": p.cooldown,
        "max_cooldown": p.max_cooldown,
        "block_meter": p.block_meter,
        "block_meter_max": p.block_meter_max,
        "blocking": p.blocking,
        "charging": p.charging,
        "charge": p.charge,
        "score": room.scores.get(p.id, 0),
        "round_wins": room.round_wins.get(p.id, 0),
        "coins": p.coins,
        "cards": list(p.cards),
        "silenced": p.silence_timer > 0,
        "poison": p.poison,
        "cold": p.cold_timer > 0,
    }


def bot_snap(b: Bot) -> dict[str, Any]:
    return {
        "id": b.id,
        "x": b.x,
        "y": b.y,
        "width": b.width,
        "height": b.height,
        "hp": b.hp,
        "max_hp": b.max_hp,
        "customization": _customization(b.customization),
    }


def bullet_snap(b: Bullet) -> dict[str, Any]:
    return {
        "id": b.id,
        "x": b.x,
        "y": b.y,
        "size": b.size,
        "owner": b.owner,
        "color": b.color,
    }


def zone_snap(z: Zone) -> dict[str, Any]:
    return {"type": z.type, "x": z.x, "y": z.y, "radius": z.radius}


def _available_cards(room: Room) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cid in room.available_cards:
        info = card_info(cid)
        if info:
            out.append(info)
    return out


def snapshot(room: Room) -> dict[str, Any]:
    """60Hz 로 브로드캐스트되는 전체 상태(PROTOCOL §3 Snapshot)."""
    return {
        "type": "state",
        "tick": room.tick,
        "phase": room.phase,
        "mode": room.mode,
        "players": [player_snap(room, p) for p in room.players.values()],
        "bots": [bot_snap(b) for b in room.bots.values()],
        "bullets": [bullet_snap(b) for b in room.bullets if b.active],
        "zones": [zone_snap(z) for z in room.zones],
        "platforms": [dict(p) for p in room.platforms],
        "loser_to_pick": room.loser_to_pick,
        "available_cards": _available_cards(room),
        "winner_id": room.winner_id,
    }


def room_state(room: Room) -> dict[str, Any]:
    """로비/대기실용 경량 상태(PROTOCOL §3 RoomState)."""
    return {
        "code": room.code,
        "mode": room.mode,
        "max_players": room.max_players,
        "phase": room.phase,
        "players": [
            {
                "id": p.id,
                "nickname": p.nickname,
                "customization": _customization(p.customization),
                "coins": p.coins,
            }
            for p in room.players.values()
        ],
    }
