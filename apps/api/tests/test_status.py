"""상태이상은 플레이어에게도 봇에게도 똑같이 걸려야 한다.

봇(Bot)에는 poison/cold/dazzle/silence 필드 자체가 없어서, 훈련장에서는
SILENCE·COLD BULLETS·POISON·DAZZLE 과 EMP·STATIC FIELD·FROST SLAM 장판이
통째로 무효였다. 대전에서만 되고 훈련장에서는 안 되니 "구현이 안 된" 것으로 보였다.
"""

from __future__ import annotations

import pytest

from app.game import bullets, cards, constants as C, sim
from app.game.bots import create_bot, update_bot
from app.game.models import Player
from app.game.rooms import RoomManager


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _pvp_room(manager: RoomManager):
    room = manager.create("pvp", 2, map_id="classic")
    room.phase = "playing"
    return room


def _add_player(room, pid: str = "a", x: float = 100.0, y: float = 300.0) -> Player:
    p = Player(id=pid, nickname=pid, x=x, y=y)
    p.aim.x, p.aim.y = x + 200.0, y
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _hit(room, shooter: Player, target) -> None:
    """shooter 의 탄을 target 몸통에 정확히 맞힌다."""
    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = target.cx - bullet.vx, target.cy
    room.bullets.append(bullet)
    bullets.update_bullets(room)


# --------------------------------------------------------------------------
# SILENCE — 맞으면 1초 동안 총을 못 쏜다
# --------------------------------------------------------------------------


def test_silence_stops_a_player_from_shooting(manager: RoomManager) -> None:
    room = _pvp_room(manager)
    shooter = _add_player(room)
    target = _add_player(room, "b", x=600.0)
    cards.apply_card(shooter, "silence")

    _hit(room, shooter, target)
    assert target.silence_timer == 60, "1초(60틱) 동안 침묵"

    room.bullets.clear()
    target.cooldown = 0.0
    bullets.fire(room, target)
    assert not room.bullets, "침묵 중에는 한 발도 못 나간다"

    for _ in range(60):
        sim.update_player(room, target)
    target.cooldown = 0.0
    bullets.fire(room, target)
    assert room.bullets, "1초가 지나면 다시 쏠 수 있다"


def test_silence_stops_a_bot_from_shooting(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    player = _add_player(room)
    bot = create_bot(room, "veteran")
    bot.x, bot.y = player.x + 200.0, player.y
    cards.apply_card(player, "silence")

    # 대조군: 멀쩡한 봇은 이 자리에서 잘 쏜다(테스트가 헛돌지 않게 확인).
    for _ in range(30):
        bot.cooldown = 0.0
        update_bot(room, bot)
    assert room.bullets, "봇이 원래 쏘는 상황이어야 의미가 있다"

    _hit(room, player, bot)
    assert bot.silence_timer == 60

    room.bullets.clear()
    for _ in range(30):
        bot.cooldown = 0.0
        update_bot(room, bot)
    assert not room.bullets, "침묵 중인 봇은 총을 못 쏜다"


# --------------------------------------------------------------------------
# 기절 장판 — EMP / STATIC FIELD (가드하면 주변이 굳는다)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("card", ["emp", "static_field"])
def test_guard_zone_stuns_a_nearby_player(manager: RoomManager, card: str) -> None:
    room = _pvp_room(manager)
    p = _add_player(room)
    enemy = _add_player(room, "b", x=p.x + 20.0)
    enemy.y = p.y
    cards.apply_card(p, card)
    p.inputs.block = True

    for _ in range(sim.GUARD_PERIOD * 2):
        sim.update_player(room, p)
        sim.update_zones(room)
        room.tick += 1

    assert enemy.dazzle_timer > 0, "가드 장판에 닿은 적은 굳어야 한다"
    assert enemy.silence_timer > 0
    assert p.dazzle_timer == 0, "내 장판에 내가 굳으면 안 된다"


@pytest.mark.parametrize("card", ["emp", "static_field"])
def test_guard_zone_stuns_a_nearby_bot(manager: RoomManager, card: str) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    p = _add_player(room)
    bot = create_bot(room, "veteran")
    bot.x, bot.y = p.x + 20.0, p.y
    cards.apply_card(p, card)
    p.inputs.block = True

    for _ in range(sim.GUARD_PERIOD * 2):
        sim.update_player(room, p)
        sim.update_zones(room)
        room.tick += 1

    assert bot.dazzle_timer > 0
    assert bot.silence_timer > 0


def test_a_stunned_bot_stops_moving(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    _add_player(room)
    bot = create_bot(room, "veteran")
    bot.dazzle_timer = 30
    bot.vx = 0.0

    for _ in range(10):
        update_bot(room, bot)

    assert bot.vx == pytest.approx(0.0, abs=0.01)


# --------------------------------------------------------------------------
# 나머지 상태이상도 봇에게 걸린다
# --------------------------------------------------------------------------


def test_cold_slows_a_bot_down(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    player = _add_player(room)
    bot = create_bot(room, "veteran")
    bot.x, bot.y = player.x + 200.0, player.y
    cards.apply_card(player, "cold_bullets")

    _hit(room, player, bot)
    assert bot.cold_timer > 0

    bot.dir = 1
    for _ in range(40):
        update_bot(room, bot)

    assert bot.vx <= bot.speed * 0.65 + 0.01, "얼면 최고 속도가 깎여야 한다"


def test_poison_keeps_ticking_on_a_bot(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    player = _add_player(room)
    bot = create_bot(room, "veteran")
    bot.x, bot.y = player.x + 200.0, player.y
    cards.apply_card(player, "poison")

    _hit(room, player, bot)
    assert bot.poison == 10

    hp_after_hit = bot.hp
    for _ in range(300):  # 5초
        room.tick += 1
        update_bot(room, bot)

    assert bot.poison == 0
    assert hp_after_hit - bot.hp == pytest.approx(10.0)


def test_dazzle_bullet_stuns_a_bot(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    room.phase = "playing"
    player = _add_player(room)
    bot = create_bot(room, "veteran")
    bot.x, bot.y = player.x + 200.0, player.y
    cards.apply_card(player, "dazzle")

    _hit(room, player, bot)

    assert bot.dazzle_timer >= C.DAZZLE_HIT_TICKS - 1
