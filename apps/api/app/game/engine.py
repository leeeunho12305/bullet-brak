"""1틱 시뮬레이션 진입점 + 라운드/매치 판정.

엔티티 물리는 `app.game.sim` 이 담당한다(PROTOCOL §6 파일 400줄 제한).
FastAPI/WebSocket 을 절대 import 하지 않는다(순수 로직, 테스트 가능).
레거시 server/index.js 의 setInterval 틱 루프를 이식했다.
"""

from __future__ import annotations

import random
from typing import Any, Literal

from app.game import constants as C
from app.game import maps, sim, training
from app.game.bullets import update_bullets
from app.game.cards import apply_card, random_cards, reset_card_state
from app.game.models import Room
from app.game.physics import clamp

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

    # 훈련장은 라운드/점수가 없다. 웨이브 진행과 부활은 training 이 따로 판정한다.
    if room.mode == "training" and room.phase == "playing":
        training.tick(room)


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
    # 훈련장은 라운드가 없다(training.tick 이 웨이브/부활로 대신한다).
    if room.mode != "pvp":
        return
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


def open_card_pick(room: Room) -> None:
    """훈련장 웨이브 클리어 보상. 카드 5장을 열어 준다(training 이 호출)."""
    player = next(iter(room.players.values()), None)
    if player is None:
        return
    room.phase = "picking"
    room.loser_to_pick = player.id
    room.available_cards = _pick_card_ids(C.CARD_CHOICES)


def _resolve_round_over(room: Room) -> None:
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


def random_spawn(room: Room | None = None) -> tuple[float, float]:
    """맵에 정의된 스폰 지점 하나. 맵을 모르면 월드 상단 랜덤."""
    points = maps.spawn_points(room)
    return random.choice(points) if points else maps.fallback_spawn()


def _place_players(room: Room) -> None:
    """라운드 시작 배치. 스폰 지점을 섞어 겹치지 않게 나눠 준다."""
    points = maps.spawn_points(room)
    random.shuffle(points)
    for i, p in enumerate(room.players.values()):
        if not points:
            x, y = maps.fallback_spawn()
        else:
            x, y = points[i % len(points)]
            if i >= len(points):  # 스폰 지점보다 사람이 많으면 자리를 재사용하므로 흩뜨린다
                x += random.uniform(-45.0, 45.0)
        p.x = clamp(x, 0.0, C.WIDTH - p.width)
        p.y = y


def prepare_map(room: Room) -> None:
    """라운드 시작 전 맵 확정.

    방장이 "무작위"를 골랐다면 ROUNDS 처럼 라운드마다 새 맵을 뽑는다.
    훈련장은 낙사 없는 맵에서만 고른다(봇 상대로 떨어지면 연습이 안 된다).
    """
    if room.map_id == maps.RANDOM_ID:
        pool = maps.TRAINING_SAFE_IDS if room.mode == "training" else None
        maps.apply(room, maps.random_id(exclude=room.active_map_id, pool=pool))
    elif room.active_map_id != room.map_id:
        maps.apply(room, room.map_id)


def set_map(room: Room, map_id: str) -> bool:
    """방장의 맵 선택. 대기실 / 매치 종료 상태에서만 바꿀 수 있다."""
    if room.phase not in ("waiting", "finished"):
        return False
    if not maps.is_valid_selection(map_id):
        return False
    room.map_id = map_id
    if map_id != maps.RANDOM_ID:
        maps.apply(room, map_id)
    return True


def reset_round(room: Room) -> None:
    """다음 라운드 준비. 카드 효과(스탯)는 유지한다."""
    if room.phase == "finished":
        return
    prepare_map(room)
    room.phase = "playing"
    room.round_end_timer = 0
    room.loser_to_pick = None
    room.available_cards = []
    room.bullets.clear()
    room.zones.clear()
    _ROUND_WINNER.pop(room.code, None)

    _place_players(room)
    for p in room.players.values():
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
        # 훈련장을 처음부터 다시 시작한다(다음 틱에 1웨이브가 스폰된다).
        room.bots.clear()
        room.bot_seq = 0
        if room.training is not None:
            room.training.wave = 0
            room.training.survived_ticks = 0


def reset_match(room: Room) -> None:
    """매치 전체 초기화(리매치). 카드/스탯을 기본값으로 되돌린다."""
    room.scores.clear()
    room.round_wins.clear()
    room.rematch_votes.clear()
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
    room.rematch_votes.clear()
    room.winner_id = None
    reset_round(room)
    return True


#: vote_rematch 의 반환값
RematchResult = Literal["ignored", "pending", "start", "declined"]


def vote_rematch(room: Room, player_id: str, accept: bool) -> RematchResult:
    """매치 종료 후 "한 판 더?" 투표.

    한 명이라도 거절하면 대기실로 돌아가고, 전원 동의하면 곧바로 새 매치를 시작한다.
    """
    if room.phase != "finished" or player_id not in room.players:
        return "ignored"

    if not accept:
        reset_match(room)  # phase -> waiting (대기실로)
        return "declined"

    room.rematch_votes.add(player_id)
    # 혼자 남은 방에서는 상대를 기다린다(둘이 되면 방장이 다시 시작한다).
    if len(room.players) < 2 or not room.rematch_votes.issuperset(room.players):
        return "pending"

    reset_match(room)  # 카드/스탯 초기화 + phase -> waiting
    start_game(room)  # 대기실을 거치지 않고 바로 다음 매치로
    return "start"


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
    if room.mode == "training":
        # 훈련장은 라운드를 리셋하지 않는다. 카드를 챙기고 다음 웨이브로 넘어간다.
        room.phase = "playing"
        training.next_wave(room)
    else:
        reset_round(room)
    return True
