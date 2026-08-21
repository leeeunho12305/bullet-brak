"""스냅샷 직렬화. PROTOCOL §3 의 키 이름/구조를 그대로 만든다.

dataclass 를 통째로 dump 하지 않는다(내부 flags/타이머 유출 금지).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from app.game import constants as C
from app.game import maps, training
from app.game.cards import card_info
from app.game.models import Bot, Bullet, Player, Room, Zone
from app.game.stats import damage_table, stat_summary


def _axis(value: Any) -> float:
    """파츠 오프셋 한 축. 숫자가 아니거나 범위를 벗어나면 잘라낸다."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(f):
        return 0.0
    return max(-C.MAX_PART_OFFSET, min(C.MAX_PART_OFFSET, f))


def _offsets(raw: Any) -> dict[str, dict[str, float]]:
    """아는 슬롯의, 0이 아닌 오프셋만 내보낸다(대역폭)."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for slot in C.PART_SLOTS:
        value = raw.get(slot)
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if not isinstance(value, dict):
            continue
        x = _axis(value.get("x"))
        y = _axis(value.get("y"))
        if x or y:
            out[slot] = {"x": x, "y": y}
    return out


def _customization(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "eye": int(raw.get("eye", 0)),
        "mouth": int(raw.get("mouth", 0)),
        "detail": int(raw.get("detail", 0)),
        "detail2": int(raw.get("detail2", 0)),
        "color": str(raw.get("color", "#ff6b6b")),
        "offsets": _offsets(raw.get("offsets")),
    }


def player_snap(room: Room, p: Player, loadout: bool = True) -> dict[str, Any]:
    """loadout=False 면 카드를 먹을 때만 바뀌는 필드(stats/damage_table)를 뺀다."""
    snap: dict[str, Any] = {
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
        "guard_broken": p.guard_broken,
        "charging": p.charging,
        "charge": p.charge,
        "score": room.scores.get(p.id, 0),
        "round_wins": room.round_wins.get(p.id, 0),
        "coins": p.coins,
        "cards": list(p.cards),
        "silenced": p.silence_timer > 0,
        "poison": p.poison,
        "cold": p.cold_timer > 0,
        "stunned": p.dazzle_timer > 0,
        # 정지 충전(WIND UP / CAREFUL PLANNING / RITUAL COUNTDOWN)의 게이지.
        "windup": p.windup,
    }
    # Tab 오버레이용. 매 틱 보내면 스냅샷의 38% 를 차지해서 0.5초에 한 번만 싣는다.
    # 클라이언트는 마지막으로 받은 값을 유지한다(PROTOCOL §3).
    if loadout:
        snap["stats"] = stat_summary(p)
        snap["damage_table"] = damage_table(p)
    return snap


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
        "tier": b.tier,
        "aim": {"x": b.aim.x, "y": b.aim.y},
        # 봇도 플레이어와 같은 상태이상을 받는다(훈련장에서 카드가 통해야 한다).
        "silenced": b.silence_timer > 0,
        "poison": b.poison,
        "cold": b.cold_timer > 0,
        "stunned": b.dazzle_timer > 0,
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


#: 대전 중 loadout 필드를 싣는 주기(틱). 60Hz 기준 0.5초.
LOADOUT_INTERVAL = 30


def snapshot(room: Room) -> dict[str, Any]:
    """60Hz 로 브로드캐스트되는 전체 상태(PROTOCOL §3 Snapshot)."""
    # 전투 중이 아니면(대기/카드선택/종료) 트래픽이 한가하므로 매 틱 싣는다.
    loadout = room.phase != "playing" or room.tick % LOADOUT_INTERVAL == 0
    return {
        "type": "state",
        "tick": room.tick,
        "phase": room.phase,
        "mode": room.mode,
        # 테마/이름 같은 무거운 필드는 room_state 로만 보낸다(맵이 바뀌면 서버가 다시 쏜다).
        "map_id": room.active_map_id,
        "players": [player_snap(room, p, loadout) for p in room.players.values()],
        "bots": [bot_snap(b) for b in room.bots.values()],
        "bullets": [bullet_snap(b) for b in room.bullets if b.active],
        "zones": [zone_snap(z) for z in room.zones],
        "platforms": [dict(p) for p in room.platforms],
        "loser_to_pick": room.loser_to_pick,
        "available_cards": _available_cards(room),
        "winner_id": room.winner_id,
        # 리매치에 동의한 사람들(finished 에서만 찬다). PROTOCOL §3 Snapshot.rematch
        "rematch": [pid for pid in room.players if pid in room.rematch_votes],
        "training": training.snap(room),
    }


def room_state(room: Room) -> dict[str, Any]:
    """로비/대기실용 경량 상태(PROTOCOL §3 RoomState)."""
    return {
        "code": room.code,
        "mode": room.mode,
        "max_players": room.max_players,
        "phase": room.phase,
        # map_id 는 방장이 고른 값("random" 일 수 있고), map 은 지금 깔린 실제 맵이다.
        "map_id": room.map_id,
        "map": maps.get(room.active_map_id).to_dict(),
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
