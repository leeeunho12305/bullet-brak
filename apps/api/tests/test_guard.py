"""가드(라운드당 횟수 제한)와 가드/장판 효과 검증.

가드는 게이지가 아니다 — 누른 순간 1회를 쓰고 BLOCK_DURATION 동안만 펼쳐지며,
라운드가 다시 시작될 때만 채워진다.
"""

from __future__ import annotations

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
# 가드 = 라운드당 횟수
# --------------------------------------------------------------------------


def test_guard_lasts_a_fixed_time_and_does_not_refill_in_a_round() -> None:
    room, p = _room()
    p.inputs.block = True

    sim.update_player(room, p)
    assert p.blocking
    assert p.block_uses == 0
    assert p.block_timer == C.BLOCK_DURATION

    # 지속 시간이 끝나면 풀린다. 계속 누르고 있어도 다시 켜지지 않는다.
    for _ in range(C.BLOCK_DURATION + 60):
        sim.update_player(room, p)
    assert not p.blocking
    assert p.block_uses == 0

    # 키를 뗐다 다시 눌러도 마찬가지다 — 라운드 안에서는 회복되지 않는다.
    p.inputs.block = False
    sim.update_player(room, p)
    p.inputs.block = True
    sim.update_player(room, p)
    assert not p.blocking


def test_holding_the_key_only_triggers_one_guard() -> None:
    """누르고 있는 내내 다시 발동하면 횟수 제한이 의미가 없다."""
    room, p = _room()
    p.block_uses_max = p.block_uses = 3
    p.inputs.block = True

    for _ in range(C.BLOCK_DURATION * 2 + 10):
        sim.update_player(room, p)

    assert p.block_uses == 2, "한 번 누르고 있는 동안 여러 번 소모됐다"


def test_round_reset_refills_guard() -> None:
    room, p = _room()
    room.players["b"] = Player(id="b", x=400.0, y=300.0)
    p.block_uses = 0
    p.block_timer = 10

    engine.reset_round(room)

    assert p.block_uses == p.block_uses_max == C.BLOCK_USES
    assert p.block_timer == 0
    assert not p.inputs.block_consumed


def test_defender_adds_a_use_and_shields_up_extends_the_duration() -> None:
    _, p = _room()
    cards.apply_card(p, "defender")
    cards.apply_card(p, "shields_up")

    assert p.block_uses_max == C.BLOCK_USES + 1
    assert p.block_uses == C.BLOCK_USES + 1
    assert p.block_duration == C.BLOCK_DURATION + 30


def test_empower_boosts_only_the_first_shot_after_a_guard() -> None:
    room, p = _room()
    cards.apply_card(p, "empower")
    p.inputs.block = True
    for _ in range(C.BLOCK_DURATION + 2):
        sim.update_player(room, p)
    assert p.empower_ready, "가드가 끝났는데 강화가 준비되지 않았다"

    p.cooldown = 0.0
    bullets.fire(room, p)
    boosted = room.bullets[-1].damage
    p.cooldown = 0.0
    bullets.fire(room, p)
    plain = room.bullets[-1].damage

    assert boosted == pytest.approx(plain * 1.6)
    assert not p.empower_ready


# --------------------------------------------------------------------------
# 가드 장판
# --------------------------------------------------------------------------


def test_guard_zones_spawn_once_per_guard() -> None:
    """예전에는 가드가 유지되는 내내 6틱마다 뿌려서 회복량이 몇 배로 뻥튀기됐다."""
    room, p = _room()
    cards.apply_card(p, "healing_field")
    p.inputs.block = True

    for _ in range(C.BLOCK_DURATION):
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
