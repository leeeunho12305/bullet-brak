"""1틱 시뮬레이션 + 라운드/매치 판정.

FastAPI/WebSocket 을 절대 import 하지 않는다(순수 로직, 테스트 가능).
레거시 server/index.js 의 setInterval 틱 루프를 이식했다.
"""

from __future__ import annotations

import math
import random
from typing import Any

from app.game import bullets as _bullets
from app.game import constants as C
from app.game.bots import create_bot, respawn_bot, update_bot
from app.game.bullets import update_bullets
from app.game.cards import apply_card, random_cards, reset_card_state
from app.game.models import Bot, Player, Room, Zone
from app.game.physics import clamp, resolve_platform_collision

#: 라운드 종료 시점의 승자 id 를 방 코드별로 기억(타이머 만료 때 사용).
_ROUND_WINNER: dict[str, str | None] = {}

#: 가드 중 생성되는 장판: (카드 플래그, 존 타입, 반경, 지속틱)
_GUARD_ZONES: tuple[tuple[str, str, float, int], ...] = (
    ("radiance", "radiance", 100.0, 18),
    ("healing_field", "heal", 120.0, 60),
    ("shockwave", "shockwave", 110.0, 1),
    ("implode", "implode", 140.0, 30),
    ("static_field", "static", 130.0, 45),
    ("emp", "emp", 120.0, 12),
    ("frost_slam", "frost", 120.0, 14),
)

#: 소유자에게는 적용하지 않는 장판 타입
_HARMFUL_ZONES = frozenset({"toxic", "static", "emp", "frost", "implode", "shockwave", "chilling"})

#: 가드 장판/톱날 생성 주기(레거시는 매 틱 생성 → 장판 폭증. 성능상 6틱마다로 제한)
_GUARD_PERIOD = 6

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
            _update_player(room, player)
        _update_bots(room)
        update_bullets(room)
        _update_zones(room)
        if room.phase == "playing":
            _check_fall_death(room)
        _judge(room)

    _maintain_training(room)


# --------------------------------------------------------------------------
# 플레이어
# --------------------------------------------------------------------------


def _update_player(room: Room, p: Player) -> None:
    if not p.alive:
        _corpse_physics(room, p)
        return

    if p.cooldown > 0:
        p.cooldown -= 1
    if p.charging:
        p.charge = clamp(p.charge + 2, 0.0, C.MAX_CHARGE)

    # 상태이상 감소
    for attr in ("blood_timer", "cold_timer", "dazzle_timer", "silence_timer", "echo_cooldown"):
        value = getattr(p, attr)
        if value > 0:
            setattr(p, attr, value - 1)
    if p.poison > 0 and room.tick % 30 == 0:
        p.hp -= 1
        p.poison -= 1
        if p.hp <= 0:
            _kill(p)
            return

    # 정지 축적(WIND UP / CAREFUL PLANNING / RITUAL COUNTDOWN 용)
    p.still_ticks = p.still_ticks + 1 if (abs(p.vx) < 0.25 and abs(p.vy) < 1.5) else 0
    p.windup = clamp(p.windup + (1 if p.still_ticks > 0 else -2), 0.0, C.MAX_CHARGE)

    stunned = p.dazzle_timer > 0
    inp = p.inputs
    blocking = bool(inp.block) and p.block_meter > 0 and not stunned
    p.blocking = blocking

    if blocking:
        p.vx *= 0.5
        _guard_effects(room, p)
        p.block_meter = max(0.0, p.block_meter - (0.75 if p.has("shields_up") else C.BLOCK_DRAIN))
    else:
        if not stunned:
            if inp.left:
                p.vx -= C.ACCEL
            if inp.right:
                p.vx += C.ACCEL
            if inp.jump and p.jumps < max(1, p.max_jumps) and not inp.jump_consumed:
                p.vy = p.jump_power
                p.grounded = False
                p.jumps += 1
                inp.jump_consumed = True
        regen = 1.25 if p.has("shields_up") else C.BLOCK_REGEN
        p.block_meter = min(p.block_meter_max, p.block_meter + regen)
    if not inp.jump:
        inp.jump_consumed = False

    # 이동 / 중력 / 경계 / 발판
    speed = p.speed * (0.65 if p.cold_timer > 0 else 1.0)
    p.vx = clamp(p.vx, -speed, speed)
    if not inp.left and not inp.right:
        p.vx *= C.FRICTION

    p.vy += C.GRAVITY
    p.x += p.vx
    p.y += p.vy
    p.grounded = False

    if p.x < 0:
        p.x, p.vx = 0.0, 0.0
    elif p.x + p.width > C.WIDTH:
        p.x, p.vx = C.WIDTH - p.width, 0.0

    for plat in room.platforms:
        resolve_platform_collision(p, plat)

    if p.has("chilling_presence") and room.tick % 10 == 0:
        room.zones.append(Zone("chilling", p.cx, p.cy, 150.0, 12, p.id))


def _guard_effects(room: Room, p: Player) -> None:
    """가드 유지 중 발동하는 카드 효과(텔레포트/실드차지/장판/톱날 등)."""
    cx, cy = p.cx, p.cy
    dx, dy = p.aim.x - cx, p.aim.y - cy
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag

    if p.has("shield_charge"):
        p.vx += ux * 5
        p.vy += uy * 2
    if p.has("teleport"):
        p.x = clamp(cx + ux * 110, 0.0, C.WIDTH - p.width)
        p.y = clamp(cy + uy * 50, 0.0, C.HEIGHT - p.height)
    if p.has("tactical_reload"):
        p.cooldown = max(0.0, p.cooldown - 8)
    if p.has("scavenger"):
        p.cooldown = max(0.0, p.cooldown - 4)
    if p.has("echo") and p.echo_cooldown <= 0:
        p.flags["echo_ready"] = True

    if room.tick % _GUARD_PERIOD:
        return
    for flag, ztype, radius, duration in _GUARD_ZONES:
        if p.has(flag):
            room.zones.append(Zone(ztype, cx, cy, radius, duration, p.id))
    if p.has("saw"):
        _spawn_saw(room, p, math.atan2(uy, ux))


def _spawn_saw(room: Room, p: Player, angle: float) -> None:
    """SAW 카드: 가드 중 톱날 탄환. bullets.spawn_bullet 이 있으면만 동작."""
    spawn = getattr(_bullets, "spawn_bullet", None)
    if spawn is None:
        return
    try:
        bullet = spawn(p, angle)
        bullet.id = room.next_bullet_id()
        bullet.life = 60
        bullet.max_bounces = max(bullet.max_bounces, 3)
        room.bullets.append(bullet)
    except Exception:  # 게임코어 시그니처 불일치 시 조용히 무시
        return


def _corpse_physics(room: Room, p: Player) -> None:
    """사망 플레이어 시체는 중력만 받고 발판 위에 눕는다."""
    p.blocking = False
    p.charging = False
    p.vy += C.GRAVITY
    p.x += p.vx
    p.y += p.vy
    if p.x < 0:
        p.x, p.vx = 0.0, p.vx * -0.5
    elif p.x > C.WIDTH:
        p.x, p.vx = C.WIDTH, p.vx * -0.5
    if p.vy <= 0:
        return
    for plat in room.platforms:
        if (
            p.x + p.width > plat["x"]
            and p.x < plat["x"] + plat["width"]
            and p.y + p.height > plat["y"]
            and p.y < plat["y"] + plat["height"]
        ):
            p.y = plat["y"] - p.height
            p.vy = 0.0
            p.vx *= 0.8
            break


def _kill(p: Player) -> None:
    p.hp = 0.0
    p.vx = 0.0
    p.vy = 0.0
    p.blocking = False
    p.charging = False
    p.charge = 0.0
    p.block_meter = 0.0
    p.silence_timer = 0
    p.poison = 0


def _check_fall_death(room: Room) -> None:
    for p in room.players.values():
        if p.alive and p.y > C.HEIGHT + 100:
            _kill(p)


# --------------------------------------------------------------------------
# 봇 / 장판
# --------------------------------------------------------------------------


def _update_bots(room: Room) -> None:
    for bot in list(room.bots.values()):
        if not bot.alive:
            respawn_bot(bot)
            continue
        update_bot(bot, room.platforms)


def _maintain_training(room: Room) -> None:
    if room.mode != "training":
        return
    for bot_id, bot in list(room.bots.items()):
        if not bot.alive and bot.y > C.HEIGHT + 200:
            room.bots.pop(bot_id, None)
    if room.phase != "playing":
        return
    guard = 0
    while len(room.bots) < C.TRAINING_BOT_COUNT and guard < C.TRAINING_BOT_COUNT + 2:
        guard += 1
        bot = create_bot(room)
        if bot is not None:
            room.bots.setdefault(bot.id, bot)


def _update_zones(room: Room) -> None:
    if not room.zones:
        return
    entities = room.entities()
    for zone in room.zones:
        zone.duration -= 1
        harmful = zone.type in _HARMFUL_ZONES
        for entity in entities:
            if not entity.alive or (harmful and zone.owner == entity.id):
                continue
            _apply_zone(zone, entity)
    room.zones = [z for z in room.zones if z.duration > 0]


def _apply_zone(z: Zone, e: Player | Bot) -> None:
    dx, dy = e.cx - z.x, e.cy - z.y
    dist = math.hypot(dx, dy)
    if dist > z.radius:
        return
    power = 1.0 - dist / z.radius
    norm = max(dist, 1.0)
    kind = z.type
    is_player = isinstance(e, Player)

    if kind == "heal":
        e.hp = min(e.max_hp, e.hp + 0.8 * power)
    elif kind == "radiance":
        e.hp = min(e.max_hp, e.hp + 0.25 * power)
    elif kind == "toxic":
        e.hp -= 0.7 * power
        if is_player:
            e.poison += 1
    elif kind in ("static", "emp"):
        if is_player:
            e.silence_timer = max(e.silence_timer, 25)
            e.dazzle_timer = max(e.dazzle_timer, 20)
    elif kind == "frost":
        if is_player:
            e.cold_timer = max(e.cold_timer, 50)
    elif kind == "implode":
        e.vx += (-dx / norm) * 0.35 * power
        e.vy += (-dy / norm) * 0.35 * power
    elif kind == "shockwave":
        e.vx += (dx / norm) * 6 * power
        e.vy += (dy / norm) * 4 * power
    elif kind == "chilling":
        e.vx *= 0.92

    if is_player and e.hp <= 0:
        _kill(e)


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
        p.flags.pop("echo_ready", None)

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
