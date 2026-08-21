"""가드(라운드당 게이지)와 가드/장판 효과 검증.

가드는 게이지다 — 누르고 있는 동안만 줄고 손을 떼면 그 자리에서 멈춘다.
가득 찬 게이지(150)를 계속 눌러 다 쓰는 데 30초가 걸리고, 라운드가 다시 시작될 때만 채워진다.
"""

from __future__ import annotations

import math

import pytest

from app.game import bullets, cards, constants as C, engine, sim
from app.game.models import Player, Room, Zone


def _room() -> tuple[Room, Player]:
    room = Room(code="222222")
    room.phase = "playing"
    player = Player(id="a", x=100.0, y=300.0)
    room.players["a"] = player
    return room, player


# --------------------------------------------------------------------------
# 가드 = 라운드당 게이지
# --------------------------------------------------------------------------

#: 게이지를 끝까지 쓰는 데 걸리는 틱(= 30초)
_FULL_GUARD_TICKS = int(C.BLOCK_DRAIN_SECONDS * C.TICK_RATE)


def test_full_guard_gauge_lasts_thirty_seconds() -> None:
    room, p = _room()
    assert p.block_meter == C.BLOCK_METER_MAX == 150.0
    p.inputs.block = True

    for _ in range(_FULL_GUARD_TICKS - 1):
        sim.update_player(room, p)
    assert p.blocking, "30초가 되기 전에 가드가 풀렸다"
    assert p.block_meter > 0

    sim.update_player(room, p)
    assert p.block_meter == 0.0

    # 바닥나면 계속 누르고 있어도 다시 켜지지 않는다(라운드 안에서는 회복되지 않는다).
    sim.update_player(room, p)
    assert not p.blocking


def test_guard_can_be_released_midway_and_the_rest_is_kept() -> None:
    """중간에 끊을 수 있어야 한다 — 남은 게이지는 그대로 아껴 둔다."""
    room, p = _room()
    p.inputs.block = True
    for _ in range(300):  # 5초만 쓴다
        sim.update_player(room, p)
    left = p.block_meter
    assert left == pytest.approx(C.BLOCK_METER_MAX - C.BLOCK_DRAIN * 300)

    p.inputs.block = False
    for _ in range(120):
        sim.update_player(room, p)
    assert not p.blocking, "키를 뗐는데도 가드가 유지됐다"
    assert p.block_meter == left, "가드를 끊었는데 게이지가 계속 줄었다"

    # 남은 만큼 다시 쓸 수 있다.
    p.inputs.block = True
    sim.update_player(room, p)
    assert p.blocking
    assert p.block_meter < left


def test_round_reset_refills_guard() -> None:
    room, p = _room()
    room.players["b"] = Player(id="b", x=400.0, y=300.0)
    p.block_meter = 0.0

    engine.reset_round(room)

    assert p.block_meter == p.block_meter_max == C.BLOCK_METER_MAX


def test_defender_adds_gauge_and_shields_up_slows_the_drain() -> None:
    _, p = _room()
    cards.apply_card(p, "defender")
    cards.apply_card(p, "shields_up")

    assert p.block_meter_max == C.BLOCK_METER_MAX + 75.0
    assert p.block_meter == C.BLOCK_METER_MAX + 75.0
    assert p.block_drain == pytest.approx(C.BLOCK_DRAIN * 0.7)


def test_empower_boosts_only_the_first_shot_after_a_guard() -> None:
    room, p = _room()
    cards.apply_card(p, "empower")
    p.inputs.block = True
    for _ in range(30):
        sim.update_player(room, p)
    assert not p.empower_ready, "가드 중인데 벌써 강화가 준비됐다"

    p.inputs.block = False  # 중간에 끊는다
    sim.update_player(room, p)
    assert p.empower_ready, "가드를 끊었는데 강화가 준비되지 않았다"

    p.cooldown = 0.0
    bullets.fire(room, p)
    boosted = room.bullets[-1].damage
    p.cooldown = 0.0
    bullets.fire(room, p)
    plain = room.bullets[-1].damage

    assert boosted == pytest.approx(plain * 1.6)
    assert not p.empower_ready


# --------------------------------------------------------------------------
# 가드 반사
# --------------------------------------------------------------------------


def test_a_reflected_bullet_actually_flies_back() -> None:
    """예전에는 반사가 도탄으로 세어져서, 도탄 카드가 없는 보통 탄(max_bounces=0)이
    반사되자마자 `bounces > max_bounces` 검사에 걸려 다음 틱에 사라졌다 —
    "막아도 되돌아가는 탄이 안 보인다"의 정체다."""
    room, blocker = _room()
    attacker = Player(id="b", x=700.0, y=0.0)  # 되돌아간 탄의 경로에서 비켜 세운다
    room.players["b"] = attacker
    blocker.blocking = True

    bullet = bullets.spawn_bullet(room, attacker, math.pi)  # 왼쪽(blocker) 으로
    bullet.x, bullet.y = blocker.cx, blocker.cy
    room.bullets = [bullet]

    bullets._hit_players(room, bullet)
    assert bullet.owner == blocker.id
    assert bullet.vx > 0, "반사했는데 방향이 그대로다"

    for _ in range(20):
        bullets.update_bullets(room)

    assert bullet.active, "반사한 탄이 곧바로 사라졌다"
    assert bullet.x > blocker.cx + 100, "반사한 탄이 날아가지 않았다"


def test_a_reflected_bullet_can_hit_the_original_shooter() -> None:
    room, blocker = _room()
    attacker = Player(id="b", x=400.0, y=300.0)
    room.players["b"] = attacker
    blocker.blocking = True

    bullet = bullets.spawn_bullet(room, attacker, math.pi)
    bullet.x, bullet.y = blocker.cx, blocker.cy
    room.bullets = [bullet]
    bullets._hit_players(room, bullet)

    before = attacker.hp
    for _ in range(60):
        bullets.update_bullets(room)
        if attacker.hp < before:
            break

    assert attacker.hp < before, "반사한 탄이 쏜 사람에게 닿지 않았다"


# --------------------------------------------------------------------------
# 가드 장판
# --------------------------------------------------------------------------


def test_guard_zones_spawn_once_per_guard() -> None:
    """예전에는 가드가 유지되는 내내 6틱마다 뿌려서 회복량이 몇 배로 뻥튀기됐다."""
    room, p = _room()
    cards.apply_card(p, "healing_field")
    p.inputs.block = True

    for _ in range(180):  # 3초 동안 계속 누르고 있어도 한 장뿐이어야 한다
        sim.update_player(room, p)

    assert len([z for z in room.zones if z.type == "heal"]) == 1


def test_healing_field_does_not_heal_the_enemy_standing_in_it() -> None:
    room, p = _room()
    enemy = Player(id="b", x=100.0, y=300.0)
    enemy.hp = 50.0
    room.players["b"] = enemy
    room.zones.append(Zone("heal", p.cx, p.cy, 120.0, 30, p.id))

    for _ in range(30):
        sim.update_zones(room)

    assert enemy.hp == 50.0, "내 회복 장판이 상대까지 살려 줬다"


def test_healing_field_does_not_heal_an_enemy_bot_either() -> None:
    """훈련장에서도 같다 — 내 회복 장판은 나만 회복한다."""
    from app.game.bots import create_bot

    room, p = _room()
    room.mode = "training"
    bot = create_bot(room, "dummy")
    bot.x, bot.y = p.x, p.y
    bot.hp = 20.0
    room.zones.append(Zone("heal", p.cx, p.cy, 120.0, 60, p.id))

    for _ in range(60):
        sim.update_zones(room)

    assert bot.hp == 20.0, "내 회복 장판이 봇까지 살려 줬다"


def test_radiance_on_hit_lands_under_the_shooter_not_the_victim() -> None:
    """radiance 는 소유자만 회복하는 장판이다. 맞은 쪽 발밑에 깔면 회복은 안 되면서
    "회복 장판이 적을 살린다"는 그림만 남는다."""
    room, shooter = _room()
    victim = Player(id="b", x=600.0, y=300.0)
    room.players["b"] = victim
    cards.apply_card(shooter, "radiance")

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = victim.cx, victim.cy
    bullets._damage_player(room, bullet, victim)

    zone = next(z for z in room.zones if z.type == "radiance")
    assert (zone.x, zone.y) == (shooter.cx, shooter.cy)
    assert zone.owner == shooter.id


def test_implode_pulls_an_enemy_toward_the_center() -> None:
    """속도만 건드리던 시절에는 마찰에 지워져서 아무도 끌려오지 않았다."""
    room, p = _room()
    enemy = Player(id="b", x=200.0, y=300.0)
    room.players["b"] = enemy
    cards.apply_card(p, "implode")
    p.aim.x, p.aim.y = 200.0, 300.0
    p.inputs.block = True

    sim.update_player(room, p)  # 가드 시작 → implode 장판 생성
    assert any(z.type == "implode" for z in room.zones)

    before = enemy.x
    for _ in range(30):
        sim.update_zones(room)

    assert enemy.x < before - 20, "끌어당김이 눈에 띄게 움직이지 않았다"


def test_toxic_cloud_is_weak_per_tick_but_lasts_four_seconds() -> None:
    room, p = _room()
    victim = Player(id="b", x=100.0, y=300.0)
    room.players["b"] = victim
    room.zones.append(
        Zone("toxic", victim.cx, victim.cy, C.TOXIC_RADIUS, C.TOXIC_TICKS, p.id)
    )

    sim.update_zones(room)
    assert victim.max_hp - victim.hp < 1.0, "한 틱에 아픈 장판이면 '오래 깔린다'가 무의미하다"

    for _ in range(C.TOXIC_TICKS - 1):
        sim.update_zones(room)

    assert not room.zones, "4초가 지나도 구름이 남아 있다"
    total = victim.max_hp - victim.hp
    assert 30.0 < total < 40.0
