"""테스트 부트스트랩.

게임코어 모듈(cards/physics/bullets/bots)이 아직 없을 때만 최소 스텁을 주입한다.
실제 모듈이 생기면 이 파일은 아무 것도 하지 않는다. (통합 후 삭제 가능)
"""

from __future__ import annotations

import importlib
import math
import random
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.game  # noqa: E402
from app.game import constants as C  # noqa: E402


def _exists(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def _register(short: str, module: types.ModuleType) -> None:
    sys.modules[f"app.game.{short}"] = module
    setattr(app.game, short, module)


# -- cards -----------------------------------------------------------------
if not _exists("app.game.cards"):
    m = types.ModuleType("app.game.cards")

    class _Card:
        def __init__(self, cid: str) -> None:
            self.id = cid
            self.name = cid.upper()
            self.desc = ""
            self.category = "attack"
            self.color = "#ffffff"
            self.emoji = "*"

    m.CARDS = [_Card(f"stub_card_{i}") for i in range(8)]
    m.CARD_BY_ID = {c.id: c for c in m.CARDS}
    m.card_info = lambda cid: (
        {
            "id": c.id,
            "name": c.name,
            "desc": c.desc,
            "category": c.category,
            "color": c.color,
            "emoji": c.emoji,
        }
        if (c := m.CARD_BY_ID.get(cid))
        else None
    )
    m.card_infos = lambda: [m.card_info(c.id) for c in m.CARDS]
    m.random_cards = lambda n=5: random.sample(m.CARDS, min(n, len(m.CARDS)))

    def _apply(player, card_id):  # type: ignore[no-untyped-def]
        if card_id not in m.CARD_BY_ID:
            return False
        player.cards.append(card_id)
        return True

    m.apply_card = _apply
    m.reset_card_state = lambda player: None
    _register("cards", m)

# -- physics ---------------------------------------------------------------
if not _exists("app.game.physics"):
    m = types.ModuleType("app.game.physics")
    m.clamp = lambda v, lo, hi: lo if v < lo else (hi if v > hi else v)

    def _resolve(entity, rect):  # type: ignore[no-untyped-def]
        if not (
            entity.x < rect["x"] + rect["width"]
            and entity.x + entity.width > rect["x"]
            and entity.y < rect["y"] + rect["height"]
            and entity.y + entity.height > rect["y"]
        ):
            return
        if entity.vy > 0:
            entity.y = rect["y"] - entity.height
            entity.vy = 0.0
            entity.grounded = True
            entity.jumps = 0

    m.resolve_platform_collision = _resolve
    m.bullet_hits_rect = lambda b, r: (
        r["x"] <= b.x <= r["x"] + r["width"] and r["y"] <= b.y <= r["y"] + r["height"]
    )

    def _explode(room, x, y, owner_id, damage, radius=90.0, knockback=14.0):  # type: ignore[no-untyped-def]
        for e in room.entities():
            d = math.hypot(e.cx - x, e.cy - y)
            if 0 < d <= radius:
                e.hp -= damage * (1 - d / radius)

    m.apply_explosion = _explode
    _register("physics", m)

# -- bullets ---------------------------------------------------------------
if not _exists("app.game.bullets"):
    m = types.ModuleType("app.game.bullets")
    from app.game.models import Bullet  # noqa: E402

    def _spawn(player, angle, **extra):  # type: ignore[no-untyped-def]
        return Bullet(
            id=0,
            owner=player.id,
            x=player.cx,
            y=player.cy,
            vx=math.cos(angle) * C.BASE_BULLET_SPEED,
            vy=math.sin(angle) * C.BASE_BULLET_SPEED,
        )

    def _fire(room, player):  # type: ignore[no-untyped-def]
        angle = math.atan2(player.aim.y - player.cy, player.aim.x - player.cx)
        b = _spawn(player, angle)
        b.id = room.next_bullet_id()
        room.bullets.append(b)
        return b

    def _update(room):  # type: ignore[no-untyped-def]
        for b in room.bullets:
            b.x += b.vx
            b.y += b.vy
            b.life -= 1
            if b.life <= 0:
                b.active = False
        room.bullets = [b for b in room.bullets if b.active]

    m.spawn_bullet = _spawn
    m.fire = _fire
    m.fire_strong = _fire
    m.update_bullets = _update
    _register("bullets", m)

# -- bots ------------------------------------------------------------------
if not _exists("app.game.bots"):
    m = types.ModuleType("app.game.bots")
    from app.game.models import Bot  # noqa: E402

    def _create(room):  # type: ignore[no-untyped-def]
        room.bot_seq += 1
        bot = Bot(id=f"bot-{room.bot_seq}", x=100.0 + random.random() * 600.0, y=150.0)
        room.bots[bot.id] = bot
        return bot

    def _respawn(bot):  # type: ignore[no-untyped-def]
        bot.x, bot.y = 100.0 + random.random() * 600.0, 0.0
        bot.vx = bot.vy = 0.0
        bot.hp = bot.max_hp

    def _update_bot(bot, platforms):  # type: ignore[no-untyped-def]
        bot.vy += C.GRAVITY
        bot.x += bot.vx
        bot.y += bot.vy

    m.create_bot = _create
    m.respawn_bot = _respawn
    m.update_bot = _update_bot
    _register("bots", m)
