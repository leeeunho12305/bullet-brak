"""BURST: 부채꼴 산탄이 아니라 같은 방향 연발이어야 한다.

예전에는 fire() 가 burst 를 발수 곱셈으로 처리해서 한 틱에 3발이 퍼져 나갔다
(= 산탄). 지금은 첫 발만 즉시 나가고 나머지는 BURST_INTERVAL 틱마다 같은
각도로 이어 나간다.
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
    p.aim.x, p.aim.y = x + 200.0, y  # 오른쪽 정면 조준
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _angles(room) -> list[float]:
    return [math.atan2(b.vy, b.vx) for b in room.bullets]


def _tick(room, p: Player, ticks: int) -> None:
    for _ in range(ticks):
        sim.update_player(room, p)
        room.tick += 1


# --------------------------------------------------------------------------


def test_burst_fires_one_bullet_at_a_time(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    assert len(room.bullets) == 1, "누른 순간에는 한 발만 나간다(산탄이 아니다)"

    _tick(room, p, C.BURST_INTERVAL)
    assert len(room.bullets) == 2

    _tick(room, p, C.BURST_INTERVAL)
    assert len(room.bullets) == 3

    _tick(room, p, C.BURST_INTERVAL * 3)
    assert len(room.bullets) == 3, "3발로 끝나야 한다"


def test_burst_bullets_all_go_the_same_way(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    _tick(room, p, C.BURST_INTERVAL * 2)

    angles = _angles(room)
    assert len(angles) == 3
    assert max(angles) - min(angles) < 1e-9, "같은 방향으로 나가야 한다"


def test_burst_keeps_the_original_angle_even_if_aim_moves(manager: RoomManager) -> None:
    """누른 순간의 방향으로 나간다 — 쏘는 도중 마우스를 돌려도 따라가지 않는다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    first = _angles(room)[0]
    p.aim.x, p.aim.y = p.cx, p.cy - 300.0  # 조준을 위로 홱 돌린다

    _tick(room, p, C.BURST_INTERVAL * 2)

    assert all(abs(a - first) < 1e-9 for a in _angles(room))


def test_burst_volley_keeps_buckshot_spread(manager: RoomManager) -> None:
    """BUCKSHOT 과 겹치면 '퍼지는 산탄'을 3연발로 쏜다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")
    cards.apply_card(p, "buckshot")

    bullets.fire(room, p)
    assert len(room.bullets) == 4  # buckshot 3 + 1

    _tick(room, p, C.BURST_INTERVAL * 2)
    assert len(room.bullets) == 12  # 4발 산탄 × 3연발
    assert len(set(round(a, 6) for a in _angles(room))) == 4, "각 연발이 같은 부채꼴이어야 한다"


def test_burst_does_not_need_the_cooldown_to_be_ready(manager: RoomManager) -> None:
    """예약된 발은 재장전 중에도 나간다(연발이 끊기면 점사가 아니다)."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    assert p.cooldown > 0

    _tick(room, p, C.BURST_INTERVAL * 2)

    assert len(room.bullets) == 3


def test_silence_cuts_the_burst_off(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    p.silence_timer = 120

    _tick(room, p, C.BURST_INTERVAL * 3)

    assert len(room.bullets) == 1
    assert p.burst_queue == 0


def test_death_cuts_the_burst_off(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "burst")

    bullets.fire(room, p)
    p.hp = 0.0

    _tick(room, p, C.BURST_INTERVAL * 3)

    assert len(room.bullets) == 1
    assert p.burst_queue == 0


def test_no_burst_card_means_a_single_shot(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)

    bullets.fire(room, p)
    _tick(room, p, C.BURST_INTERVAL * 3)

    assert len(room.bullets) == 1
