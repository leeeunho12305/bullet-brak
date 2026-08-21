"""넉백과 피격 반응.

두 가지를 지킨다.
  1. 넉백은 실제로 밀어야 한다 — 예전에는 다음 틱의 이동 속도 clamp 와 마찰이 통째로
     지워 버려서, 낙사 맵이 아니면 아무 의미가 없었다.
  2. 그렇다고 위로 쏘아 올리면 안 된다 — 명중 한 번마다 `vy -= 4` 를 더하던 시절에는
     산탄 4알·연발 3발이 겹치면서 맞은 쪽이 점프보다 높이 솟구쳤다.
"""

from __future__ import annotations

import pytest

from app.game import bullets, cards, constants as C, sim
from app.game.models import Player, Room


def _room() -> tuple[Room, Player, Player]:
    room = Room(code="333333")
    room.phase = "playing"
    shooter = Player(id="s", x=100.0, y=300.0)
    target = Player(id="t", x=400.0, y=300.0)
    room.players["s"] = shooter
    room.players["t"] = target
    return room, shooter, target


def _hit(room: Room, shooter: Player, target: Player) -> None:
    """탄환 한 발을 target 한가운데에 꽂는다."""
    bullet = bullets.spawn_bullet(room, shooter, 0.0)  # 오른쪽으로 수평 발사
    bullet.x, bullet.y = target.cx, target.cy
    bullets._damage_player(room, bullet, target)


# --------------------------------------------------------------------------
# 넉백이 살아남는가
# --------------------------------------------------------------------------


def test_hit_pushes_the_target_along_the_bullet() -> None:
    room, shooter, target = _room()
    _hit(room, shooter, target)

    assert target.vx > target.speed, "넉백이 이동 속도조차 넘지 못한다"


def test_knockback_survives_the_movement_speed_clamp() -> None:
    """예전에는 다음 틱에 speed 로 잘리고 마찰까지 먹어서 넉백이 사라졌다."""
    room, shooter, target = _room()
    _hit(room, shooter, target)
    pushed = target.vx

    sim.update_player(room, target)  # 입력 없음

    assert target.vx > target.speed, "한 틱 만에 이동 속도까지 깎였다"
    assert target.vx < pushed, "밀린 속도가 식지 않는다(영원히 미끄러진다)"


def test_knockback_fades_within_about_a_second() -> None:
    room, shooter, target = _room()
    _hit(room, shooter, target)

    for _ in range(60):
        sim.update_player(room, target)

    assert abs(target.vx) <= target.speed, "1초가 지나도 넉백이 남아 있다"


def test_big_bullet_pushes_harder() -> None:
    room, shooter, target = _room()
    plain = Player(id="u", x=400.0, y=300.0)
    room.players["u"] = plain
    cards.apply_card(shooter, "big_bullet")

    _hit(room, shooter, target)
    strong = target.vx

    shooter.knockback_mult = 1.0  # 같은 상황에서 배율만 뺀다
    _hit(room, shooter, plain)

    assert strong > plain.vx


# --------------------------------------------------------------------------
# 위로는 못 쏘아 올린다
# --------------------------------------------------------------------------


def test_a_single_hit_never_lifts_higher_than_a_jump() -> None:
    room, shooter, target = _room()
    _hit(room, shooter, target)

    assert target.vy >= -C.MAX_HIT_LIFT
    assert target.vy > C.JUMP_POWER


def test_a_full_shotgun_volley_does_not_launch_the_target() -> None:
    """산탄 4알 + 점사 3발 = 12발이 한꺼번에 맞아도 점프보다 높이 뜨면 안 된다."""
    room, shooter, target = _room()
    cards.apply_card(shooter, "buckshot")
    cards.apply_card(shooter, "burst")
    target.hp = 9_999.0  # 넉백만 본다

    for _ in range(12):
        _hit(room, shooter, target)

    assert target.vy >= -C.MAX_HIT_LIFT, "여러 발이 겹쳐 로켓처럼 솟았다"


def test_being_shot_while_jumping_does_not_boost_the_jump() -> None:
    room, shooter, target = _room()
    target.vy = C.JUMP_POWER  # 막 점프한 상태

    _hit(room, shooter, target)

    assert target.vy >= C.JUMP_POWER, "피격이 점프를 더 높이 밀어 올렸다"


def test_explosions_also_respect_the_lift_cap() -> None:
    from app.game.physics import apply_explosion

    room, shooter, target = _room()
    target.x, target.y = shooter.x, shooter.y + 40.0  # 바로 아래에서 터진다

    for _ in range(5):
        apply_explosion(room, target.cx, target.cy + 20.0, shooter.id, 1.0, 90.0, 40.0)

    assert target.vy >= -C.MAX_HIT_LIFT


# --------------------------------------------------------------------------
# 봇도 같은 규칙을 쓴다
# --------------------------------------------------------------------------


def test_bots_are_pushed_by_bullets_too() -> None:
    from app.game.bots import create_bot

    room = Room(code="333334")
    room.mode = "training"
    room.phase = "playing"
    shooter = Player(id="s", x=100.0, y=300.0)
    room.players["s"] = shooter
    bot = create_bot(room, "dummy")
    bot.x, bot.y = 400.0, 300.0
    bot.vx = 0.0

    bullet = bullets.spawn_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = bot.cx, bot.cy
    room.bullets = [bullet]
    bullets._hit_bots(room, bullet)

    assert bot.vx > bot.speed
    assert bot.vy >= -C.MAX_HIT_LIFT


def test_scatter_falloff_is_much_steeper_than_normal() -> None:
    from app.game.stats import falloff_at

    assert falloff_at(0, scatter=True) == pytest.approx(falloff_at(0))
    assert falloff_at(260, scatter=True) < falloff_at(260)
    assert falloff_at(260, scatter=True) == pytest.approx(C.SCATTER_FAR_MULT)


def test_buckshot_volley_cannot_one_shot_a_full_health_player() -> None:
    """4알 × 근접 30 = 120 = 최대 체력. 예전에는 붙기만 하면 즉사였다."""
    room, shooter, target = _room()
    cards.apply_card(shooter, "buckshot")
    shooter.aim.x, shooter.aim.y = target.cx, target.cy
    shooter.x = target.x  # 코앞

    bullets.fire(room, shooter)
    assert len(room.bullets) == 4
    for bullet in list(room.bullets):
        bullet.x, bullet.y = target.cx, target.cy
        bullets._damage_player(room, bullet, target)

    assert target.hp > 0, "산탄 한 방에 만피가 죽는다"


def test_buckshot_is_nearly_useless_at_range() -> None:
    room, shooter, target = _room()
    cards.apply_card(shooter, "buckshot")

    total = 0.0
    for _ in range(4):
        bullet = bullets.spawn_bullet(room, shooter, 0.0, scatter=True)
        bullet.x, bullet.y = target.cx, target.cy
        bullet.start_x, bullet.start_y = target.cx - 400.0, target.cy
        before = target.hp
        bullets._damage_player(room, bullet, target)
        total += before - target.hp

    assert total < 12.0, f"400px 밖 산탄이 아직 {total:.1f} 나 아프다"
