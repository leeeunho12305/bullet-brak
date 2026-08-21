"""가드: 시간이 아니라 "막아 낸 만큼" 닳는다 / 가드 중 점프.

- 게이지가 시간으로 닳던 시절에는 누르고 있어도 10초 뒤에 가드가 저절로 내려가서,
  가드로 켜지는 장판 카드(RADIANCE / HEALING FIELD / EMP ...)가 "시간이 지나면
  자동으로 꺼지는" 것처럼 보였다. 지금은 탄을 받아쳤을 때만 닳는다.
- 가드는 이동만 둔하게 만들 뿐 점프를 막지 않는다.
"""

from __future__ import annotations

import math

import pytest

from app.game import bullets, cards, constants as C, sim
from app.game.models import Player
from app.game.rooms import RoomManager


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _playing_room(manager: RoomManager):
    room = manager.create("pvp", 2, map_id="classic")
    room.phase = "playing"
    return room


def _add_player(room, pid: str = "a", x: float = 100.0, y: float = 100.0) -> Player:
    p = Player(id=pid, nickname=pid, x=x, y=y)
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _hold(room, p: Player, ticks: int) -> None:
    for _ in range(ticks):
        sim.update_player(room, p)
        room.tick += 1


def _recover_ticks(p: Player) -> int:
    """깨진 가드가 다시 설 때까지 걸리는 틱."""
    return math.ceil(p.block_meter_max * C.BLOCK_RECOVER_RATIO / C.BLOCK_REGEN) + 2


def _shoot_at(room, guard: Player, shots: int = 1) -> None:
    """가드 중인 guard 에게 탄을 shots 발 먹인다(= 게이지를 깎는 유일한 방법)."""
    attacker = room.players.get("atk") or _add_player(room, "atk", x=600.0)
    for _ in range(shots):
        bullet = bullets.spawn_bullet(room, attacker, 0.0)
        # 한 틱 이동한 뒤 몸통 한복판에 닿도록 둔다.
        bullet.x, bullet.y = guard.cx - bullet.vx, guard.cy
        room.bullets.append(bullet)
        bullets.update_bullets(room)
        room.bullets.clear()  # 되받아친 탄은 이 테스트에 필요 없다


def _break_guard(room, p: Player) -> None:
    """게이지를 다 깎아 가드를 깨뜨린다."""
    for _ in range(40):
        if p.block_meter <= 0:
            break
        _shoot_at(room, p)
    _hold(room, p, 1)
    assert p.guard_broken


# --------------------------------------------------------------------------
# 가드 브레이크
# --------------------------------------------------------------------------


def test_guard_never_times_out_while_held(manager: RoomManager) -> None:
    """아무도 안 쏘면 30초를 눌러도 가드가 안 내려간다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "healing_field")
    p.inputs.block = True

    _hold(room, p, 60 * 30)

    assert p.blocking, "시간이 지났다고 가드가 저절로 꺼지면 안 된다"
    assert not p.guard_broken
    assert p.block_meter == p.block_meter_max, "안 맞았으면 게이지도 그대로다"
    assert any(z.type == "heal" for z in room.zones), "장판도 계속 깔려 있어야 한다"


def test_guard_drains_only_when_it_actually_blocks_something(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    p.inputs.block = True
    _hold(room, p, 30)
    assert p.block_meter == p.block_meter_max

    _shoot_at(room, p)

    assert p.block_meter < p.block_meter_max, "막아 낸 만큼은 닳아야 한다"


def test_guard_breaks_after_blocking_enough_shots(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    p.inputs.block = True
    _hold(room, p, 1)

    _break_guard(room, p)

    assert not p.blocking, "게이지가 0 이면 버튼을 눌러도 가드가 서면 안 된다"


def test_broken_guard_recharges_while_the_button_is_held(manager: RoomManager) -> None:
    """버튼을 놓지 않아도 게이지가 다시 찬다."""
    room = _playing_room(manager)
    p = _add_player(room)
    p.inputs.block = True
    _hold(room, p, 1)
    _break_guard(room, p)

    _hold(room, p, _recover_ticks(p))

    assert not p.guard_broken
    assert p.blocking, "회복이 끝났으면 누르고 있던 가드가 다시 서야 한다"


def test_healing_field_keeps_healing_across_a_guard_break(manager: RoomManager) -> None:
    """HEALING FIELD: 가드가 깨졌다 회복된 뒤에도 장판이 다시 깔린다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "healing_field")
    p.inputs.block = True
    _hold(room, p, 1)
    _break_guard(room, p)
    room.zones.clear()

    # 깨져 있는 동안에는 계속 눌러도 장판이 안 깔린다.
    _hold(room, p, _recover_ticks(p) // 2)
    assert p.guard_broken
    assert not room.zones, "가드가 깨진 동안에는 장판이 깔리면 안 된다"

    # 회복이 끝나면 누르고 있던 가드가 다시 서고 장판도 다시 깔린다.
    _hold(room, p, _recover_ticks(p) + sim.GUARD_PERIOD * 2)

    assert any(z.type == "heal" for z in room.zones), "가드가 돌아왔으면 회복 장판도 돌아와야 한다"


def test_radiance_zone_spawns_on_every_guard_period(manager: RoomManager) -> None:
    """RADIANCE 장판이 틱 위상과 무관하게 꾸준히 깔린다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "radiance")
    p.inputs.block = True

    _hold(room, p, sim.GUARD_PERIOD * 4)

    assert sum(1 for z in room.zones if z.type == "radiance") >= 3


# --------------------------------------------------------------------------
# 가드 중 점프
# --------------------------------------------------------------------------


def test_player_can_jump_while_guarding(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    p.inputs.block = True
    p.inputs.jump = True

    sim.update_player(room, p)

    assert p.vy < 0, "가드 중에도 점프는 된다"
    assert p.blocking, "점프해도 가드는 유지된다"
    assert p.jumps == 1


def test_guard_jump_still_costs_a_jump(manager: RoomManager) -> None:
    """가드 중 점프도 점프 횟수를 쓴다(누르고 있다고 계속 뜨지 않는다)."""
    room = _playing_room(manager)
    p = _add_player(room)
    p.inputs.block = True
    p.inputs.jump = True

    _hold(room, p, 10)

    assert p.jumps == 1


def test_stun_still_blocks_the_jump(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    p.dazzle_timer = 30
    p.inputs.jump = True

    sim.update_player(room, p)

    assert p.jumps == 0
    assert p.vy > 0, "기절 중에는 중력만 받는다"
