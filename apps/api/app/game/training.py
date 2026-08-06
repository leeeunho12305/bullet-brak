"""훈련장 진행. 웨이브 스폰 / 전멸·사망 판정 / 성적 집계.

training 모드 방에서만 동작하고, pvp 방에서는 모든 함수가 조용히 빠져나간다.
FastAPI/WebSocket 을 import 하지 않는다(순수 로직).

훈련장은 대전과 규칙이 다르다 — 라운드도 점수도 매치 승리도 없다.
  웨이브 전멸 → wave_clear(1.5초) → picking(카드) → 다음 웨이브
  플레이어 사망 → respawning(3초) → 같은 웨이브를 처음부터 (카드는 유지)
"""

from __future__ import annotations

import random
from typing import Any

from app.game import constants as C
from app.game import maps
from app.game.bots import create_bot
from app.game.models import Room, TrainingState

#: 통계 키 -> 정수로 다룰지 여부
_INT_KEYS = frozenset({"kills", "deaths", "shots", "hits"})


def ensure(room: Room) -> TrainingState | None:
    """훈련방이면 상태를 보장해서 돌려준다. 아니면 None."""
    if room.mode != "training":
        return None
    if room.training is None:
        room.training = TrainingState()
    return room.training


def record(room: Room, key: str, amount: float = 1) -> None:
    """성적 집계. 훈련방이 아니면 아무 일도 하지 않는다(호출부를 단순하게 두기 위함)."""
    state = room.training
    if state is None or not hasattr(state, key):
        return
    current = getattr(state, key)
    setattr(state, key, current + (int(amount) if key in _INT_KEYS else float(amount)))


# --------------------------------------------------------------------------
# 웨이브
# --------------------------------------------------------------------------


def wave_tiers(wave: int) -> tuple[str, ...]:
    """웨이브 번호(1부터)에 해당하는 봇 티어 구성."""
    table = C.TRAINING_WAVES
    if not table:
        return ()
    index = min(max(wave, 1), len(table)) - 1
    return table[index]


def wave_hp_scale(wave: int) -> float:
    """표를 넘어선 웨이브는 체력만 올려서 계속 이어진다."""
    extra = max(0, wave - len(C.TRAINING_WAVES))
    return min(1.0 + extra * C.TRAINING_HP_SCALE_PER_WAVE, C.TRAINING_MAX_HP_SCALE)


def start_wave(room: Room, wave: int) -> None:
    """봇을 싹 갈아엎고 해당 웨이브를 시작한다."""
    state = ensure(room)
    if state is None:
        return
    room.bots.clear()
    room.bullets.clear()
    room.zones.clear()

    tiers = wave_tiers(wave)
    scale = wave_hp_scale(wave)
    for tier in tiers:
        create_bot(room, tier, hp_scale=scale)

    state.wave = wave
    state.wave_bots = len(tiers)
    state.best_wave = max(state.best_wave, wave)
    state.state = "fighting"
    state.timer = 0


def bots_left(room: Room) -> int:
    return sum(1 for bot in room.bots.values() if bot.alive)


# --------------------------------------------------------------------------
# 틱 판정
# --------------------------------------------------------------------------


def tick(room: Room) -> None:
    """훈련장 1틱. engine.tick_room 이 페이즈 판정 자리에서 호출한다."""
    state = ensure(room)
    if state is None:
        return

    player = next(iter(room.players.values()), None)
    if player is None:  # 아직 아무도 접속하지 않은 방
        return

    if state.wave == 0:  # 첫 진입
        start_wave(room, 1)
        return

    if state.state == "respawning":
        _tick_respawn(room, state, player)
        return
    if state.state == "wave_clear":
        _tick_wave_clear(room, state)
        return

    # 전투 중
    state.survived_ticks += 1
    _cleanup_dead_bots(room, state)

    if not player.alive:
        state.state = "respawning"
        state.timer = C.TRAINING_RESPAWN_TICKS
        state.deaths += 1
        return

    if bots_left(room) == 0:
        state.state = "wave_clear"
        state.timer = C.TRAINING_WAVE_BREAK_TICKS


def _cleanup_dead_bots(room: Room, state: TrainingState) -> None:
    """죽은 봇을 치우면서 킬을 센다. 시체를 남기지 않는 대신 즉시 사라진다."""
    dead = [bot_id for bot_id, bot in room.bots.items() if not bot.alive]
    for bot_id in dead:
        room.bots.pop(bot_id, None)
        state.kills += 1


def _tick_respawn(room: Room, state: TrainingState, player: Any) -> None:
    state.timer -= 1
    if state.timer > 0:
        return
    # 같은 웨이브를 처음부터. 카드/스탯은 그대로 두는 게 훈련장의 요점이다.
    player.hp = player.max_hp
    player.vx = player.vy = 0.0
    points = maps.spawn_points(room)
    player.x, player.y = random.choice(points) if points else maps.fallback_spawn()
    player.grounded = False
    player.jumps = 0
    player.cooldown = 0.0
    player.charging = False
    player.charge = 0.0
    player.block_meter = player.block_meter_max
    player.poison = 0
    player.cold_timer = player.dazzle_timer = player.silence_timer = 0
    player.echo_cooldown = player.blood_timer = 0
    player.inputs.jump_consumed = False
    state.survived_ticks = 0
    start_wave(room, state.wave)


def _tick_wave_clear(room: Room, state: TrainingState) -> None:
    from app.game.engine import open_card_pick  # 순환 import 회피

    state.timer -= 1
    if state.timer > 0:
        return
    state.timer = 0
    open_card_pick(room)


def next_wave(room: Room) -> None:
    """카드 선택이 끝나면 engine 이 호출한다."""
    state = ensure(room)
    if state is None:
        return
    start_wave(room, state.wave + 1)


# --------------------------------------------------------------------------
# 직렬화
# --------------------------------------------------------------------------


def snap(room: Room) -> dict[str, Any] | None:
    """PROTOCOL §3 TrainingSnap. 훈련방이 아니면 None."""
    state = room.training
    if state is None or room.mode != "training":
        return None
    return {
        "wave": state.wave,
        "bots_left": bots_left(room),
        "wave_bots": state.wave_bots,
        "state": state.state,
        "timer": state.timer,
        "kills": state.kills,
        "deaths": state.deaths,
        "best_wave": state.best_wave,
        "shots": state.shots,
        "hits": state.hits,
        "damage_dealt": round(state.damage_dealt, 1),
        "damage_taken": round(state.damage_taken, 1),
        "survived_ticks": state.survived_ticks,
    }
