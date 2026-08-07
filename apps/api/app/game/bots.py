"""훈련장 봇. 티어별 전투 AI(조준 / 사격 / 회피 / 추격).

기존 구현은 랜덤으로 걷고 가끔 점프하는 허수아비였다. 훈련이 되려면 봇이 실제로
쏘고 피해야 하므로 티어(dummy/rookie/veteran)를 두고 행동을 나눴다.
티어 파라미터는 constants.BOT_TIERS 가 단일 출처다.

FastAPI/WebSocket 을 import 하지 않는다(순수 로직).
"""

from __future__ import annotations

import math
import random

from app.game import blocks
from app.game import constants as C
from app.game.models import Bot, Player, Room
from app.game.physics import resolve_platform_collision

#: 이 거리보다 가까우면 물러나고, 멀면 다가간다.
NEAR_DISTANCE = 190.0
FAR_DISTANCE = 380.0

#: 회피 판정: 이 거리 안으로 들어온 적 탄환만 위협으로 본다.
THREAT_RADIUS = 150.0
EVADE_TICKS = 22

#: 사격 쿨다운에 섞는 흔들림(±%). 봇 셋이 같은 박자로 쏘면 패턴이 읽힌다.
COOLDOWN_JITTER = 0.25


# --------------------------------------------------------------------------
# 생성 / 사망
# --------------------------------------------------------------------------


def _spawn_point() -> tuple[float, float]:
    """상단 랜덤 위치. 플레이어가 대응할 시간을 주려고 공중에서 떨어뜨린다."""
    return 80.0 + random.random() * (C.WIDTH - 160.0), 40.0 + random.random() * 60.0


def create_bot(room: Room, tier: str = "rookie", hp_scale: float = 1.0) -> Bot:
    """티어 봇을 만들어 room.bots 에 등록한다."""
    traits = dict(C.BOT_TIERS.get(tier, C.BOT_TIERS["rookie"]))
    x, y = _spawn_point()
    hp = traits["hp"] * max(0.1, hp_scale)
    bot = Bot(
        id=f"bot-{room.bot_seq}",
        x=x,
        y=y,
        hp=hp,
        max_hp=hp,
        speed=traits["speed"],
        jump_power=traits["jump_power"],
        tier=tier,
        traits=traits,
        customization={
            "eye": random.randrange(5),
            "mouth": random.randrange(5),
            "detail": random.randrange(5),
            "detail2": random.randrange(4),
            "color": random.choice(C.AVATAR_PALETTE),
        },
    )
    bot.aim.x, bot.aim.y = bot.cx, bot.cy
    room.bot_seq += 1
    room.bots[bot.id] = bot
    return bot


def kill_bot(bot: Bot) -> None:
    """즉사. 방에서 치우는 것은 training._cleanup_dead_bots 가 한다."""
    bot.hp = 0.0
    bot.vx = 0.0
    bot.vy = 0.0


# --------------------------------------------------------------------------
# 인지
# --------------------------------------------------------------------------


def _nearest_player(room: Room, bot: Bot) -> Player | None:
    best: Player | None = None
    best_dist = float("inf")
    for player in room.players.values():
        if not player.alive:
            continue
        dist = math.hypot(player.cx - bot.cx, player.cy - bot.cy)
        if dist < best_dist:
            best_dist = dist
            best = player
    return best


def has_line_of_sight(room: Room, x1: float, y1: float, x2: float, y2: float) -> bool:
    """두 점 사이를 발판이 가로막지 않는가. 사선을 등분해 표본만 검사한다."""
    samples = C.BOT_SIGHT_SAMPLES
    for i in range(1, samples):
        t = i / samples
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        for plat in room.platforms:
            if (
                plat["x"] <= px <= plat["x"] + plat["width"]
                and plat["y"] <= py <= plat["y"] + plat["height"]
            ):
                return False
    return True


def _incoming_threat(room: Room, bot: Bot) -> float | None:
    """봇에게 다가오는 적 탄환의 방향(x부호)을 돌려준다. 없으면 None."""
    for bullet in room.bullets:
        if not bullet.active or bullet.owner in room.bots:
            continue
        dx = bot.cx - bullet.x
        dy = bot.cy - bullet.y
        if math.hypot(dx, dy) > THREAT_RADIUS:
            continue
        # 탄환이 멀어지는 중이면 위협이 아니다(내적 > 0 이어야 접근 중).
        if bullet.vx * dx + bullet.vy * dy <= 0:
            continue
        return math.copysign(1.0, dx) if dx else 1.0
    return None


# --------------------------------------------------------------------------
# 조준 / 사격
# --------------------------------------------------------------------------


def _aim_at(bot: Bot, target: Player) -> None:
    """조준점 갱신. 정예는 상대 속도를 읽고 미리 쏜다(선도 사격)."""
    tx, ty = target.cx, target.cy
    if bot.trait("lead") > 0:
        dist = math.hypot(tx - bot.cx, ty - bot.cy)
        travel = dist / C.BOT_BULLET_SPEED
        tx += target.vx * travel
        # 중력까지 맞추면 너무 정확해진다. 수직은 절반만 예측한다.
        ty += target.vy * travel * 0.5

    error = bot.trait("aim_error")
    if error > 0:
        angle = math.atan2(ty - bot.cy, tx - bot.cx) + random.uniform(-error, error)
        dist = math.hypot(tx - bot.cx, ty - bot.cy)
        tx = bot.cx + math.cos(angle) * dist
        ty = bot.cy + math.sin(angle) * dist

    bot.aim.x, bot.aim.y = tx, ty


def _try_fire(room: Room, bot: Bot, target: Player, has_los: bool) -> None:
    from app.game.bullets import spawn_bot_bullet  # 지연 import (순환 방지)

    cooldown = bot.trait("fire_cooldown")
    if cooldown <= 0 or bot.cooldown > 0:  # 허수아비는 cooldown 이 0 이라 영영 못 쏜다
        return
    if not has_los:  # 발판 너머로는 쏘지 않는다
        return
    dist = math.hypot(target.cx - bot.cx, target.cy - bot.cy)
    if dist > bot.trait("range"):
        return

    angle = math.atan2(bot.aim.y - bot.cy, bot.aim.x - bot.cx)
    room.bullets.append(spawn_bot_bullet(room, bot, angle))
    bot.cooldown = cooldown * random.uniform(1.0 - COOLDOWN_JITTER, 1.0 + COOLDOWN_JITTER)


# --------------------------------------------------------------------------
# 이동
# --------------------------------------------------------------------------


def _wander(bot: Bot) -> None:
    """추격할 대상이 없을 때(그리고 허수아비의 평소 행동)."""
    if bot.ai_timer <= 0:
        bot.dir = 0 if random.random() < 0.35 else random.choice((-1, 1))
        bot.ai_timer = 20 + random.randrange(80)
    bot.ai_timer -= 1
    if bot.grounded and bot.jump_cooldown == 0 and random.random() < 0.02:
        _jump(bot)


def _chase(room: Room, bot: Bot, target: Player, has_los: bool) -> None:
    """거리 유지 + 회피 + 발판 오르내리기."""
    dx = target.cx - bot.cx
    dist = abs(dx)
    toward = math.copysign(1.0, dx) if dx else 1.0

    if bot.evade_timer > 0:
        bot.evade_timer -= 1
        bot.dir = int(-toward)  # 회피 중에는 사선에서 벗어난다
    elif not has_los:
        # 발판이 시야를 가리면 사거리와 무관하게 붙는다. 이러면 발판 끝에서
        # 떨어지면서 자연스럽게 아래층으로 내려온다(안 그러면 위에서 멀뚱히 서 있는다).
        bot.dir = int(toward)
    elif dist < NEAR_DISTANCE:
        bot.dir = int(-toward)
    elif dist > FAR_DISTANCE:
        bot.dir = int(toward)
    else:
        # 사거리 안이면 좌우로 흔들어 맞기 어렵게 만든다.
        if bot.ai_timer <= 0:
            bot.dir = random.choice((-1, 0, 1))
            bot.ai_timer = 25 + random.randrange(35)
        bot.ai_timer -= 1

    # 플레이어가 위에 있으면 발판을 타고 올라간다.
    # 한 번에 올라갈 수 있는 높이는 점프력²/(2·중력) ≈ 187px 인데 층간 간격이 150px 이라,
    # 시야가 막힌 동안은 확률이 아니라 매번 뛰어야 중간 발판을 밟고 올라온다.
    above = bot.cy - target.cy
    if bot.grounded and bot.jump_cooldown == 0:
        if not has_los and above > 40:
            _jump(bot)
        elif above > 60 and random.random() < 0.06:
            _jump(bot)
        elif bot.evade_timer > 0 and random.random() < 0.25:
            _jump(bot)


def _jump(bot: Bot) -> None:
    bot.vy = bot.jump_power
    bot.grounded = False
    bot.jump_cooldown = 40


def _physics(bot: Bot, room: Room) -> None:
    if bot.dir == -1:
        bot.vx -= 1.2
    elif bot.dir == 1:
        bot.vx += 1.2

    bot.vx = max(-bot.speed, min(bot.speed, bot.vx))
    if bot.dir == 0:
        bot.vx *= blocks.ICE_FRICTION if bot.on_ice else C.FRICTION

    blocks.carry(bot, room)

    bot.vy += C.GRAVITY
    bot.x += bot.vx
    bot.y += bot.vy
    bot.grounded = False
    bot.on_ice = False

    if bot.x < 0:
        bot.x = 0.0
        bot.vx = 0.0
    elif bot.x + bot.width > C.WIDTH:
        bot.x = C.WIDTH - bot.width
        bot.vx = 0.0
    # 플레이어와 같은 천장(sim.update_player). 바닥은 뚫려 있다(낙사).
    if bot.y < 0:
        bot.y = 0.0
        bot.vy = 0.0

    # 블럭 효과(점프대/빙판/가시)는 플레이어와 같은 규칙으로 봇에게도 적용된다.
    damage = 0.0
    for index, plat in enumerate(room.platforms):
        side = resolve_platform_collision(bot, plat)
        damage += blocks.on_contact(bot, plat, side, index)
    if damage > 0:
        bot.hp -= damage
        if bot.hp <= 0:
            kill_bot(bot)


# --------------------------------------------------------------------------
# 1틱
# --------------------------------------------------------------------------


def update_bot(room: Room, bot: Bot) -> None:
    """봇 1틱: 타이머 → 인지/조준 → 사격 → 이동 → 물리."""
    if bot.cooldown > 0:
        bot.cooldown -= 1
    if bot.jump_cooldown > 0:
        bot.jump_cooldown -= 1
    if bot.reaction_timer > 0:
        bot.reaction_timer -= 1

    target = _nearest_player(room, bot)
    fights = target is not None and bot.trait("fire_cooldown") > 0

    if fights and target is not None:
        # 시야 판정은 사격과 이동이 함께 쓰므로 틱당 한 번만 계산한다.
        has_los = has_line_of_sight(room, bot.cx, bot.cy, target.cx, target.cy)

        if bot.reaction_timer <= 0:
            _aim_at(bot, target)
            bot.reaction_timer = bot.trait("reaction")

        dodge = bot.trait("dodge")
        if dodge > 0 and bot.evade_timer == 0 and _incoming_threat(room, bot) is not None:
            if random.random() < dodge:
                bot.evade_timer = EVADE_TICKS

        _try_fire(room, bot, target, has_los)
        _chase(room, bot, target, has_los)
    else:
        # 허수아비는 조준점을 자기 위치에 두어 클라이언트가 시선을 그리지 않게 한다.
        bot.aim.x, bot.aim.y = bot.cx, bot.cy
        _wander(bot)

    _physics(bot, room)


def fall_check(room: Room) -> None:
    """봇도 낙사한다(폭발 넉백으로 맵 밖에 나갈 수 있다)."""
    for bot in room.bots.values():
        if bot.alive and bot.y > C.HEIGHT + 100:
            kill_bot(bot)
