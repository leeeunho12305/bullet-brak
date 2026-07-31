"""훈련 모드 봇 (server/index.js 의 createBot / respawnBot / updateBot 포팅)."""

from __future__ import annotations

import random

from app.game import constants as C
from app.game.models import Bot, Room
from app.game.physics import resolve_platform_collision


def random_spawn() -> tuple[float, float]:
    """일반 스폰 위치."""
    return 100.0 + random.random() * 600.0, 150.0


def _random_top_spawn() -> tuple[float, float]:
    """리스폰용 상단 랜덤 위치."""
    return 100.0 + random.random() * 600.0, 0.0


def create_bot(room: Room) -> Bot:
    """랜덤 외형의 봇을 만들어 room.bots 에 등록한다."""
    x, y = random_spawn()
    bot = Bot(
        id=f"bot-{room.bot_seq}",
        x=x,
        y=y,
        customization={
            "eye": random.randrange(5),
            "mouth": random.randrange(5),
            "detail": random.randrange(5),
            "color": random.choice(C.AVATAR_PALETTE),
        },
    )
    room.bot_seq += 1
    room.bots[bot.id] = bot
    return bot


def respawn_bot(bot: Bot) -> None:
    """상단 랜덤 위치로 되살린다."""
    bot.x, bot.y = _random_top_spawn()
    bot.vx = 0.0
    bot.vy = 0.0
    bot.hp = bot.max_hp
    bot.grounded = False
    bot.cooldown = 0.0
    bot.dir = 0
    bot.ai_timer = 0
    bot.jump_cooldown = 0


def update_bot(bot: Bot, platforms: list[dict[str, float]]) -> None:
    """봇 1틱: 랜덤 방향 전환 -> 점프 -> 중력/이동 -> 경계 -> 발판 충돌."""
    if bot.ai_timer <= 0:
        bot.dir = 0 if random.random() < 0.35 else random.choice((-1, 1))
        bot.ai_timer = 20 + random.randrange(80)

    bot.ai_timer -= 1
    if bot.jump_cooldown > 0:
        bot.jump_cooldown -= 1

    if bot.dir == -1:
        bot.vx -= 1.2
    elif bot.dir == 1:
        bot.vx += 1.2

    bot.vx = max(-bot.speed, min(bot.speed, bot.vx))
    if bot.dir == 0:
        bot.vx *= C.FRICTION

    if bot.grounded and bot.jump_cooldown == 0 and random.random() < 0.02:
        bot.vy = bot.jump_power
        bot.grounded = False
        bot.jump_cooldown = 40

    bot.vy += C.GRAVITY
    bot.x += bot.vx
    bot.y += bot.vy
    bot.grounded = False

    if bot.x < 0:
        bot.x = 0.0
        bot.vx = 0.0
    if bot.x + bot.width > C.WIDTH:
        bot.x = C.WIDTH - bot.width
        bot.vx = 0.0

    for plat in platforms:
        resolve_platform_collision(bot, plat)
