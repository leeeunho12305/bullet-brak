"""엔티티 1틱 시뮬레이션(플레이어 물리 / 가드 효과 / 봇 / 장판).

engine.tick_room 이 호출하는 하위 모듈. PROTOCOL §6(파일 400줄) 때문에 engine 에서 분리했다.
FastAPI/WebSocket 을 import 하지 않는다.
"""

from __future__ import annotations

import math

from app.game import blocks
from app.game import bullets as _bullets
from app.game import constants as C
from app.game.bots import fall_check as bot_fall_check
from app.game.bots import kill_bot as bot_kill
from app.game.bots import update_bot
from app.game.models import Bot, Player, Room, Zone
from app.game.physics import clamp, handle_lethal, resolve_platform_collision

#: 가드를 **시작한 틱에 한 번만** 생성되는 장판: (카드 플래그, 존 타입, 반경, 지속틱)
GUARD_ZONES: tuple[tuple[str, str, float, int], ...] = (
    ("radiance", "radiance", 110.0, 45),
    ("healing_field", "heal", 120.0, 90),
    ("shockwave", "shockwave", 130.0, 1),
    ("implode", "implode", 170.0, 60),
    ("static_field", "static", 130.0, 45),
    ("emp", "emp", 130.0, 24),
    ("frost_slam", "frost", 140.0, 20),
)

#: 소유자에게는 적용하지 않는 장판 타입
HARMFUL_ZONES = frozenset({"toxic", "static", "emp", "frost", "implode", "shockwave", "chilling"})

#: 소유자에게만 적용하는 장판 타입. 내 회복 장판이 그 위에 선 상대까지 살려 주면 안 된다.
OWNER_ONLY_ZONES = frozenset({"heal", "radiance"})

#: 게임에 아무 영향도 주지 않는 연출용 장판(폭발 섬광). 클라이언트만 쓴다.
EFFECT_ZONES = frozenset({"blast"})

#: 상태이상 타이머(매 틱 1 감소)
_TIMERS = (
    "blood_timer", "cold_timer", "dazzle_timer", "silence_timer", "echo_cooldown", "spike_grace",
)


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

    # 이번 틱의 이동 속도 상한. 입력 처리보다 먼저 구해 둔다 —
    # 가속이 이 상한을 넘겨 밀면 그 초과분이 아래에서 넉백으로 오인돼 계속 쌓인다.
    # (COLD BULLETS 는 상한을 깎고, TASTE OF BLOOD 는 올린다)
    speed = p.speed * (0.65 if p.cold_timer > 0 else 1.0) * (1.35 if p.blood_timer > 0 else 1.0)

    # 가드는 게이지다. 누르고 있는 동안만 줄고, 손을 떼면 그 자리에서 멈춘다 —
    # 언제든 끊을 수 있다. 라운드가 끝날 때까지 다시 채워지지는 않는다.
    blocking = bool(inp.block) and p.block_meter > 0 and not stunned
    started = blocking and not p.blocking
    ended = p.blocking and not blocking
    p.blocking = blocking

    if blocking:
        p.vx *= 0.5
        p.block_meter -= p.block_drain
        # 부동소수 찌꺼기(1e-13)가 남으면 게이지를 다 썼는데도 한 틱 더 막아 준다.
        if p.block_meter < 1e-6:
            p.block_meter = 0.0
        _guard_effects(room, p, started)
    else:
        # EMPOWER: 가드를 끊은(또는 게이지가 바닥난) 직후 한 발이 강화된다.
        if ended and p.has("empower"):
            p.empower_ready = True
        if not stunned:
            # 이동 입력은 speed 까지만 민다. 이미 넉백으로 더 빠르면 그 속도를 건드리지 않고
            # (반대 방향 입력으로는 줄일 수 있다) — 이 상한이 없으면 가속이 매 틱 쌓여
            # PLAYER_SPEED 와 상관없이 4배 가까운 속도로 달리게 된다.
            if inp.left:
                p.vx = max(p.vx - C.ACCEL, min(p.vx, -speed))
            if inp.right:
                p.vx = min(p.vx + C.ACCEL, max(p.vx, speed))
            if inp.jump and p.jumps < max(1, p.max_jumps) and not inp.jump_consumed:
                p.vy = p.jump_power
                p.grounded = False
                p.jumps += 1
                inp.jump_consumed = True
    if not inp.jump:
        inp.jump_consumed = False

    # 이동 / 중력 / 경계 / 발판
    over = abs(p.vx) - speed
    if over > C.KNOCKBACK_MIN:
        # 이동 입력으로 낼 수 있는 속도는 speed 까지다. 그보다 빠른 건 넉백/폭발로 얻은
        # 속도이므로 clamp 로 잘라내지도, 마찰로 지우지도 않는다. 예전에는 둘 다 했기 때문에
        # 넉백이 다음 틱에 통째로 사라졌고, 그래서 낙사 맵 말고는 아무 쓸모가 없었다.
        p.vx = math.copysign(speed + over * C.KNOCKBACK_DECAY, p.vx)
    else:
        p.vx = clamp(p.vx, -speed, speed)
        if not inp.left and not inp.right:
            # 빙판 위에서는 거의 멈추지 못한다(직전 틱의 접촉 판정을 쓴다).
            p.vx *= blocks.ICE_FRICTION if p.on_ice else C.FRICTION

    # 올라타 있던 이동발판을 따라간다(발판은 engine 이 이미 이번 틱 위치로 옮겨 뒀다).
    blocks.carry(p, room)

    p.vy += C.GRAVITY
    p.x += p.vx
    p.y += p.vy
    p.grounded = False
    p.on_ice = False

    if p.x < 0:
        p.x, p.vx = 0.0, 0.0
    elif p.x + p.width > C.WIDTH:
        p.x, p.vx = C.WIDTH - p.width, 0.0
    # 천장은 막혀 있다(점프 강화 카드나 폭발 넉백으로 화면 위로 새지 않게).
    # 바닥은 일부러 뚫려 있다 — 낙사가 협곡/부유섬 맵의 규칙이다.
    if p.y < 0:
        p.y, p.vy = 0.0, 0.0

    damage = 0.0
    for index, plat in enumerate(room.platforms):
        if not blocks.is_solid(plat):
            blocks.touch(p, plat)  # 점프대: 밀어내지 않고 튀어오르게만 한다
            continue
        side = resolve_platform_collision(p, plat)
        damage += blocks.on_contact(p, plat, side, index)
    if damage > 0:
        p.hp -= damage
        if p.hp <= 0:
            handle_lethal(p)  # 가시로도 PHOENIX(revives) 는 발동한다
            if not p.alive:
                return

    if p.has("chilling_presence") and room.tick % 10 == 0:
        room.zones.append(Zone("chilling", p.cx, p.cy, 150.0, 12, p.id))


def _guard_effects(room: Room, p: Player, started: bool) -> None:
    """가드 중 발동하는 카드 효과(실드차지/장판/톱날 등).

    장판과 톱날은 **가드를 시작한 그 틱에 한 번만** 만든다. 예전처럼 가드가 유지되는 내내
    뿌리면 같은 장판이 겹겹이 쌓여 회복량과 끌어당김이 몇 배로 뻥튀기된다.
    """
    cx, cy = p.cx, p.cy
    dx, dy = p.aim.x - cx, p.aim.y - cy
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag

    if p.has("shield_charge"):
        p.vx += ux * 5
        p.vy += uy * 2
    if p.has("tactical_reload"):
        p.cooldown = max(0.0, p.cooldown - 8)
    if p.has("scavenger"):
        p.cooldown = max(0.0, p.cooldown - 4)
    # ECHO 반격탄은 bullets._reflect 가 player.has("echo")/echo_cooldown 으로 처리한다

    if not started:
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
    # 시체도 천장에 부딪힌다(옆 벽처럼 튕겨서 다시 떨어진다)
    if p.y < 0:
        p.y, p.vy = 0.0, p.vy * -0.5
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
    """살아있는 봇만 굴린다. 죽은 봇을 치우고 다음 웨이브를 여는 것은 training 담당."""
    for bot in list(room.bots.values()):
        if not bot.alive:
            continue
        update_bot(room, bot)
    bot_fall_check(room)


# --------------------------------------------------------------------------
# 장판
# --------------------------------------------------------------------------


def update_zones(room: Room) -> None:
    if not room.zones:
        return
    entities = room.entities()
    for zone in room.zones:
        zone.duration -= 1
        if zone.type in EFFECT_ZONES:
            continue  # 폭발 섬광 — 클라이언트 연출 전용이라 아무에게도 닿지 않는다
        harmful = zone.type in HARMFUL_ZONES
        owner_only = zone.type in OWNER_ONLY_ZONES
        for entity in entities:
            if not entity.alive:
                continue
            if harmful and zone.owner == entity.id:
                continue
            if owner_only and zone.owner != entity.id:
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
        e.hp = min(e.max_hp, e.hp + 0.45 * power)
    elif kind == "radiance":
        e.hp = min(e.max_hp, e.hp + 0.25 * power)
    elif kind == "toxic":
        # 한 방이 아니라 오래 갉는 장판이다. 독 중첩도 매 틱이 아니라 주기적으로만 쌓인다.
        e.hp -= C.TOXIC_TICK_DAMAGE * power
        if is_player and z.duration % C.TOXIC_STACK_PERIOD == 0:
            e.poison += 1
    elif kind in ("static", "emp"):
        e.silence_timer = max(e.silence_timer, 25)
        e.dazzle_timer = max(e.dazzle_timer, 20)
    elif kind == "frost":
        e.cold_timer = max(e.cold_timer, 50)
    elif kind == "implode":
        # 속도만 건드리면 마찰(FRICTION)과 이동 입력 clamp 에 그대로 지워져서 아무도
        # 끌려오지 않았다. 위치를 직접 당기고 속도에도 같은 방향을 실어 준다.
        # 가장자리에서도 최소한은 끌리도록 세기의 바닥을 40% 로 둔다.
        pull = C.IMPLODE_PULL * (0.4 + 0.6 * power)
        e.x -= (dx / norm) * pull
        e.y -= (dy / norm) * pull
        e.vx -= (dx / norm) * 0.6 * power
        e.vy -= (dy / norm) * 0.6 * power
    elif kind == "shockwave":
        e.vx += (dx / norm) * 6 * power
        e.vy += (dy / norm) * 4 * power
    elif kind == "chilling":
        e.vx *= 0.92

    if e.hp <= 0:
        handle_lethal(e) if is_player else bot_kill(e)
