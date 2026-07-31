"""1틱 시뮬레이션 진입점 + 라운드/매치 판정.

엔티티 물리는 `app.game.sim` 이 담당한다(PROTOCOL §6 파일 400줄 제한).
FastAPI/WebSocket 을 절대 import 하지 않는다(순수 로직, 테스트 가능).
레거시 server/index.js 의 setInterval 틱 루프를 이식했다.
"""

from __future__ import annotations

import random
from typing import Any

from app.game import constants as C
from app.game import sim
from app.game.bullets import update_bullets
from app.game.cards import apply_card, random_cards, reset_card_state
from app.game.models import Room

#: 라운드 종료 시점의 승자 id 를 방 코드별로 기억(타이머 만료 때 사용).
_ROUND_WINNER: dict[str, str | None] = {}

ACTIVE_PHASES = ("playing", "round_over")


def forget_room(code: str) -> None:
    """방 삭제 시 내부 캐시 정리."""
    _ROUND_WINNER.pop(code, None)


# ==========================================================================
# 틱
# ==========================================================================


def tick_room(room: Room) -> None:
    """방 하나를 1틱 진행시킨다."""
    room.tick += 1

    if room.phase in ACTIVE_PHASES:
        for player in room.players.values():
            sim.update_player(room, player)
        sim.update_bots(room)
        update_bullets(room)
        sim.update_zones(room)
        if room.phase == "playing":
            sim.check_fall_death(room)
        _judge(room)

    sim.maintain_training(room)


# ==========================================================================
# 라운드 / 매치 판정
# ==========================================================================


def _judge(room: Room) -> None:
    if room.phase == "playing":
        _check_round_over(room)
        return
    if room.phase != "round_over":
        return
    room.round_end_timer -= 1
    if room.round_end_timer <= 0:
        room.round_end_timer = 0
        _resolve_round_over(room)


def _check_round_over(room: Room) -> None:
    if room.mode == "pvp":
        if len(room.players) < 2:
            return
        alive = [p for p in room.players.values() if p.alive]
        if len(alive) > 1:
            return
        winner = alive[0] if alive else None
        room.phase = "round_over"
        room.round_end_timer = C.ROUND_END_DELAY_TICKS
        _ROUND_WINNER[room.code] = winner.id if winner else None
        if winner:
            room.round_wins[winner.id] = room.round_wins.get(winner.id, 0) + 1
            winner.coins += 10
    else:  # training
        player = next(iter(room.players.values()), None)
        if player is None or player.alive:
            return
        room.phase = "round_over"
        room.round_end_timer = C.ROUND_END_DELAY_TICKS
        _ROUND_WINNER[room.code] = None


def _resolve_round_over(room: Room) -> None:
    if room.mode == "training":
        player = next(iter(room.players.values()), None)
        if player is None:
            room.phase = "waiting"
            return
        room.phase = "picking"
        room.loser_to_pick = player.id
        room.available_cards = _pick_card_ids(C.CARD_CHOICES)
        return

    winner_id = _ROUND_WINNER.pop(room.code, None)
    winner = room.players.get(winner_id) if winner_id else None
    if winner is None:
        reset_round(room)
        return

    if room.round_wins.get(winner.id, 0) < C.ROUNDS_TO_SCORE:
        reset_round(room)
        return

    room.scores[winner.id] = room.scores.get(winner.id, 0) + 1
    room.round_wins.clear()

    if room.scores[winner.id] >= C.SCORE_TO_WIN:
        room.phase = "finished"
        room.winner_id = winner.id
        winner.coins += 100
        room.bullets.clear()
        room.zones.clear()
        room.loser_to_pick = None
        room.available_cards = []
        return

    loser_id = next((pid for pid in room.players if pid != winner.id), None)
    room.phase = "picking"
    room.loser_to_pick = loser_id
    room.available_cards = _pick_card_ids(C.CARD_CHOICES)


def _pick_card_ids(n: int) -> list[str]:
    try:
        return [getattr(c, "id", c) for c in random_cards(n)]
    except Exception:
        return []


def phase_event(room: Room, prev_phase: str) -> dict[str, Any] | None:
    """페이즈 전환을 PROTOCOL §2.2 `event` 메시지로 변환(없으면 None)."""
    if room.phase == prev_phase:
        return None
    if room.phase == "round_over":
        winner_id = _ROUND_WINNER.get(room.code)
        loser_id = next((pid for pid in room.players if pid != winner_id), None)
        return _event("round_over", winner_id, loser_id)
    if room.phase == "picking":
        return _event("card_phase", None, room.loser_to_pick)
    if room.phase == "finished":
        return _event("match_over", room.winner_id, None)
    if room.phase == "playing" and prev_phase == "waiting":
        return _event("game_started", None, None)
    return None


def _event(name: str, winner_id: str | None, loser_id: str | None) -> dict[str, Any]:
    return {"type": "event", "event": name, "winner_id": winner_id, "loser_id": loser_id}


# ==========================================================================
# 리셋 / 액션
# ==========================================================================


def random_spawn() -> tuple[float, float]:
    return 100.0 + random.random() * 600.0, 150.0


def reset_round(room: Room) -> None:
    """다음 라운드 준비. 카드 효과(스탯)는 유지한다."""
    if room.phase == "finished":
        return
    room.phase = "playing"
    room.round_end_timer = 0
    room.loser_to_pick = None
    room.available_cards = []
    room.bullets.clear()
    room.zones.clear()
    _ROUND_WINNER.pop(room.code, None)

    for p in room.players.values():
        p.x, p.y = random_spawn()
        p.vx = p.vy = 0.0
        p.hp = p.max_hp
        p.cooldown = 0.0
        p.charging = False
        p.charge = 0.0
        p.windup = 0.0
        p.still_ticks = 0
        p.grounded = False
        p.jumps = 0
        p.blocking = False
        p.block_meter = p.block_meter_max
        p.poison = 0
        p.cold_timer = p.dazzle_timer = p.silence_timer = 0
        p.echo_cooldown = p.blood_timer = 0
        p.inputs.jump_consumed = False

    if room.mode == "training":
        room.bots.clear()
        room.bot_seq = 0


def reset_match(room: Room) -> None:
    """매치 전체 초기화(리매치). 카드/스탯을 기본값으로 되돌린다."""
    room.scores.clear()
    room.round_wins.clear()
    room.winner_id = None
    room.loser_to_pick = None
    room.available_cards = []
    room.bullets.clear()
    room.zones.clear()
    room.round_end_timer = 0
    _ROUND_WINNER.pop(room.code, None)

    for p in room.players.values():
        p.max_hp = C.MAX_HP
        p.hp = C.MAX_HP
        p.speed = C.PLAYER_SPEED
        p.jump_power = C.JUMP_POWER
        p.max_cooldown = C.BASE_COOLDOWN
        p.cooldown = 0.0
        p.damage_mult = 1.0
        p.knockback_mult = 1.0
        p.bullet_size = C.BASE_BULLET_SIZE
        p.bullet_speed_mult = 1.0
        p.max_bounces = 0
        p.width = p.height = C.PLAYER_SIZE
        p.block_meter_max = C.BLOCK_METER_MAX
        p.block_meter = C.BLOCK_METER_MAX
        p.charging = False
        p.charge = 0.0
        p.cards.clear()
        p.flags.clear()
        reset_card_state(p)

    room.phase = "waiting"
    room.tick = 0


def start_game(room: Room) -> bool:
    """방장이 게임 시작. waiting 에서만 유효."""
    if room.phase != "waiting" or not room.players:
        return False
    room.scores.clear()
    room.round_wins.clear()
    room.winner_id = None
    reset_round(room)
    return True


def pick_card(room: Room, player_id: str, card_id: str) -> bool:
    """패자의 카드 선택. 성공하면 다음 라운드를 시작한다."""
    if room.phase != "picking" or room.loser_to_pick != player_id:
        return False
    if card_id not in room.available_cards:
        return False
    player = room.players.get(player_id)
    if player is None or not apply_card(player, card_id):
        return False
    room.loser_to_pick = None
    room.available_cards = []
    reset_round(room)
    return True
