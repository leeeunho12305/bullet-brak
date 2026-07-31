"""거리별 대미지 감쇠 검증."""

from __future__ import annotations

import pytest

from app.game import bullets, cards, constants as C, stats
from app.game.models import Player, Room


def _room_with_two() -> tuple[Room, Player, Player]:
    room = Room(code="111111")
    shooter = Player(id="s", x=100.0, y=300.0)
    target = Player(id="t", x=400.0, y=300.0)
    room.players["s"] = shooter
    room.players["t"] = target
    return room, shooter, target


def test_falloff_curve_matches_constants() -> None:
    assert stats.falloff_at(0) == pytest.approx(C.DAMAGE_CLOSE_MULT)
    assert stats.falloff_at(C.DAMAGE_FALLOFF_RANGE) == pytest.approx(C.DAMAGE_FAR_MULT)
    assert stats.falloff_at(9999) == pytest.approx(C.DAMAGE_FAR_MULT)  # 사거리 밖은 하한 유지
    mid = stats.falloff_at(C.DAMAGE_FALLOFF_RANGE / 2)
    assert C.DAMAGE_FAR_MULT < mid < C.DAMAGE_CLOSE_MULT


def test_close_shot_hurts_more_than_long_shot() -> None:
    room, shooter, target = _room_with_two()

    # 붙어서 맞은 탄
    close = bullets.spawn_bullet(room, shooter, 0.0)
    close.x, close.y = target.cx, target.cy
    close.start_x, close.start_y = target.cx - 10.0, target.cy
    before = target.hp
    bullets._damage_player(room, close, target)
    close_damage = before - target.hp

    # 멀리서 날아온 탄
    target.hp = target.max_hp
    far = bullets.spawn_bullet(room, shooter, 0.0)
    far.x, far.y = target.cx, target.cy
    far.start_x, far.start_y = target.cx - 700.0, target.cy
    before = target.hp
    bullets._damage_player(room, far, target)
    far_damage = before - target.hp

    assert close_damage > far_damage
    assert round(close_damage) == 30  # 기본 탄 근접
    assert round(far_damage) == 8  # 기본 탄 원거리


def test_damage_mult_applied_once() -> None:
    """공격력 카드가 제곱으로 적용되면 안 된다(표와 실제가 어긋남)."""
    room, shooter, target = _room_with_two()
    cards.apply_card(shooter, "glass_cannon")  # damage_mult 1.0 -> 2.0

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = target.cx, target.cy
    bullet.start_x, bullet.start_y = target.cx, target.cy  # 거리 0
    before = target.hp
    bullets._damage_player(room, bullet, target)
    dealt = before - target.hp

    table_close = stats.damage_table(shooter)[0]["damage"]
    assert round(dealt, 1) == table_close == 60.0


def test_reflection_resets_falloff_origin() -> None:
    room, shooter, blocker = _room_with_two()
    blocker.blocking = True

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = 700.0, 300.0  # 멀리 날아온 상태
    bullets._reflect(room, bullet, blocker)

    assert (bullet.start_x, bullet.start_y) == (700.0, 300.0)
    assert bullet.owner == blocker.id
