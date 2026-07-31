"""엔티티 1틱 시뮬레이션(플레이어 물리 / 가드 효과 / 봇 / 장판).

engine.tick_room 이 호출하는 하위 모듈. PROTOCOL §6(파일 400줄) 때문에 engine 에서 분리했다.
FastAPI/WebSocket 을 import 하지 않는다.
"""

from __future__ import annotations

import math

from app.game import bullets as _bullets
from app.game import constants as C
from app.game.bots import create_bot, respawn_bot, update_bot
from app.game.models import Bot, Player, Room, Zone
from app.game.physics import clamp, handle_lethal, resolve_platform_collision

#: 가드 중 생성되는 장판: (카드 플래그, 존 타입, 반경, 지속틱)
GUARD_ZONES: tuple[tuple[str, str, float, int], ...] = (
    ("radiance", "radiance", 100.0, 18),
    ("healing_field", "heal", 120.0, 60),
    ("shockwave", "shockwave", 110.0, 1),
    ("implode", "implode", 140.0, 30),
    ("static_field", "static", 130.0, 45),
    ("emp", "emp", 120.0, 12),
    ("frost_slam", "frost", 120.0, 14),
)

#: 소유자에게는 적용하지 않는 장판 타입
HARMFUL_ZONES = frozenset({"toxic", "static", "emp", "frost", "implode", "shockwave", "chilling"})

#: 가드 장판/톱날 생성 주기(레거시는 매 틱 생성 → 장판 폭증. 성능상 6틱마다로 제한)
GUARD_PERIOD = 6

#: 상태이상 타이머(매 틱 1 감소)
_TIMERS = ("blood_timer", "cold_timer", "dazzle_timer", "silence_timer", "echo_cooldown")


# --------------------------------------------------------------------------
# 플레이어
# --------------------------------------------------------------------------


def update_player(room: Room, p: Player) -> None:
    """플레이어 1틱: 쿨다운/상태이상 → 입력/가드 → 이동/중력/발판."""
    if not p.alive:
        _corpse_physics(room, p)
        return

    if p.cooldown > 0:
        p.cooldown -= 1
    if p.charging:
        p.charge = clamp(p.charge + 2, 0.0, C.MAX_CHARGE)

    for attr in _TIMERS:
        value = getattr(p, attr)
        if value > 0:
            setattr(p, attr, value - 1)
    if p.poison > 0 and room.tick % 30 == 0:
        p.hp -= 1
        p.poison -= 1
        if p.hp <= 0:
            handle_lethal(p)  # PHOENIX(revives) 처리 포함
            if not p.alive:
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
    # ECHO 반격탄은 bullets._reflect 가 player.has("echo")/echo_cooldown 으로 처리한다

    if room.tick % GUARD_PERIOD:
        return
    for flag, ztype, radius, duration in GUARD_ZONES:
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
        bullet = spawn(room, p, angle, speed_mult=0.8, damage_mult=0.7, life=60, max_bounces=3)
    except TypeError:  # PROTOCOL §5 표기(room 인자 없음) 대비
        try:
            bullet = spawn(p, angle)
            bullet.id = room.next_bullet_id()
        except Exception:
            return
    except Exception:
        return
    room.bullets.append(bullet)


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


def kill(p: Player) -> None:
    """즉사(낙사 등). PHOENIX 부활을 적용하지 않는다."""
    p.hp = 0.0
    p.vx = 0.0
    p.vy = 0.0
    p.blocking = False
    p.charging = False
    p.charge = 0.0
    p.block_meter = 0.0
    p.silence_timer = 0
    p.poison = 0


def check_fall_death(room: Room) -> None:
    """낙사: y > HEIGHT + 100 이면 즉사."""
    for p in room.players.values():
        if p.alive and p.y > C.HEIGHT + 100:
            kill(p)


# --------------------------------------------------------------------------
# 봇
# --------------------------------------------------------------------------


def update_bots(room: Room) -> None:
    for bot in list(room.bots.values()):
        if not bot.alive:
            respawn_bot(bot)
            continue
        update_bot(bot, room.platforms)


def maintain_training(room: Room) -> None:
    """training 모드는 봇을 항상 3마리 유지한다."""
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


# --------------------------------------------------------------------------
# 장판
# --------------------------------------------------------------------------


def update_zones(room: Room) -> None:
    if not room.zones:
        return
    entities = room.entities()
    for zone in room.zones:
        zone.duration -= 1
        harmful = zone.type in HARMFUL_ZONES
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
        handle_lethal(e)
