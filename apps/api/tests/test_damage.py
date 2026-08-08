"""거리별 대미지 감쇠와 탄환 조향(유도탄) 검증."""

from __future__ import annotations

import math

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


# --------------------------------------------------------------------------
# 유도탄
# --------------------------------------------------------------------------


def test_homing_bullet_keeps_its_speed_while_turning() -> None:
    """적 코앞에서 크게 꺾여도 느려지면 안 된다(벡터를 섞으면 짧아지는 문제)."""
    room, shooter, target = _room_with_two()
    cards.apply_card(shooter, "homing")

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    speed = math.hypot(bullet.vx, bullet.vy)

    # 목표를 진행 방향의 정반대에 두면 조향이 가장 크게 걸린다.
    target.x, target.y = 0.0, 300.0
    for _ in range(20):
        bullets._steer(room, bullet)
        assert math.hypot(bullet.vx, bullet.vy) == pytest.approx(speed)


def test_homing_bullet_flies_through_walls_for_its_full_life() -> None:
    """유도탄은 벽을 뚫는다 — 일반 탄과 같은 시간(life) 동안 날아간다."""
    room, shooter, target = _room_with_two()
    room.platforms = [{"x": 200.0, "y": 0.0, "width": 40.0, "height": 600.0, "type": "solid"}]
    cards.apply_card(shooter, "homing")
    target.x = 700.0

    homing = bullets.spawn_bullet(room, shooter, 0.0)
    plain = bullets.spawn_bullet(room, Player(id="p2", x=100.0, y=500.0), 0.0)
    room.bullets = [homing, plain]

    for _ in range(30):
        bullets.update_bullets(room)

    assert homing.active, "유도탄이 벽에 막혀 사라졌다"
    assert homing.x > 240.0, "유도탄이 벽을 통과하지 못했다"
    assert not plain.active, "일반 탄은 벽에 막혀야 한다"
    assert homing.life == C.BASE_BULLET_LIFE - 30


# --------------------------------------------------------------------------
# TARGET BOUNCE / 폭발 자해 / 끌어당김 / 가드 횟수
# --------------------------------------------------------------------------


def test_target_bounce_does_not_home_before_it_bounces() -> None:
    """튕기기 전에는 그냥 직선탄이어야 한다(예전엔 발사하자마자 적을 쫓았다)."""
    room, shooter, target = _room_with_two()
    cards.apply_card(shooter, "target_bounce")
    target.x, target.y = 400.0, 0.0  # 정면이 아니라 위쪽에 세워 둔다

    bullet = bullets.spawn_bullet(room, shooter, 0.0)  # 오른쪽으로 수평 발사
    assert not bullet.has("homing")
    for _ in range(10):
        bullets._steer(room, bullet)
    assert bullet.vy == pytest.approx(0.0), "튕기지도 않았는데 적 쪽으로 꺾였다"


def test_target_bounce_homes_after_hitting_a_wall() -> None:
    room, shooter, target = _room_with_two()
    cards.apply_card(shooter, "target_bounce")

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x = C.WIDTH + 1  # 오른쪽 벽 밖
    bullets._bounce_walls(bullet)

    assert bullet.has("homing"), "벽에 튕겼는데도 추적이 켜지지 않았다"
    target.x, target.y = 400.0, 0.0
    bullets._steer(room, bullet)
    assert bullet.vy < 0, "튕긴 뒤에는 적 쪽으로 꺾여야 한다"


def test_own_explosion_never_hurts_the_shooter() -> None:
    """폭발 카드를 들었다고 자기 탄환에 자기가 깎이면 안 된다."""
    room, shooter, target = _room_with_two()
    cards.apply_card(shooter, "explosive_bullet")

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = shooter.cx, shooter.cy  # 코앞에서 터뜨린다
    target.x = shooter.x + 20.0  # 상대는 폭심지 옆

    before_shooter, before_target = shooter.hp, target.hp
    bullets._expire(room, bullet, 0.6)

    assert shooter.hp == before_shooter, "자기 폭발에 자기가 맞았다"
    assert target.hp < before_target, "상대는 폭발에 맞아야 한다"


def test_explosion_leaves_a_blast_zone_for_the_client() -> None:
    room, shooter, _ = _room_with_two()
    cards.apply_card(shooter, "explosive_bullet")
    bullet = bullets.spawn_bullet(room, shooter, 0.0)

    bullets._expire(room, bullet, 0.6)

    blasts = [z for z in room.zones if z.type == "blast"]
    assert len(blasts) == 1
    assert blasts[0].duration == C.BLAST_TICKS
