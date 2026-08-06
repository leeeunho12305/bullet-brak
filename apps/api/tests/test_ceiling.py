"""월드 경계: 천장은 막혀 있고 바닥은 뚫려 있다.

점프 강화 카드 / 폭발 넉백 / 가드 밀치기가 겹치면 화면 위로 솟구칠 수 있어서 천장을 막았다.
반대로 바닥은 일부러 열어 둔다 — 낙사가 협곡·부유섬 맵의 규칙이기 때문이다.
"""

from __future__ import annotations

import pytest

from app.game import constants as C
from app.game import engine, sim
from app.game.bots import create_bot
from app.game.models import Player
from app.game.rooms import RoomManager


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _playing_room(manager: RoomManager, map_id: str = "classic"):
    room = manager.create("pvp", 2, map_id=map_id)
    room.phase = "playing"
    return room


def _add_player(room, pid: str = "a", x: float = 100.0, y: float = 100.0) -> Player:
    p = Player(id=pid, nickname=pid, x=x, y=y)
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


# --------------------------------------------------------------------------
# 천장
# --------------------------------------------------------------------------


def test_player_cannot_pass_through_the_ceiling(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room, y=40.0)
    p.vy = -60.0  # 폭발 넉백 수준의 상승 속도

    sim.update_player(room, p)

    assert p.y == 0.0
    assert p.vy == 0.0


def test_ceiling_holds_under_sustained_upward_force(manager: RoomManager) -> None:
    """매 틱 위로 밀어도 천장을 못 뚫는다(한 번만 막고 마는 게 아니다)."""
    room = _playing_room(manager)
    p = _add_player(room, y=100.0)

    for _ in range(120):
        p.vy -= 30.0  # 계속 위로 밀어 올린다
        sim.update_player(room, p)
        assert p.y >= 0.0, f"천장을 뚫었다: y={p.y}"


def test_huge_player_still_fits_under_the_ceiling(manager: RoomManager) -> None:
    """HUGE 카드로 커진 상태에서도 머리가 화면 위로 나가지 않는다."""
    room = _playing_room(manager)
    p = _add_player(room, y=30.0)
    p.width = p.height = C.PLAYER_SIZE * 1.5
    p.vy = -40.0

    sim.update_player(room, p)

    assert p.y == 0.0


def test_bot_cannot_pass_through_the_ceiling(manager: RoomManager) -> None:
    room = manager.create("training", 1, map_id="classic")
    bot = create_bot(room, "rookie")
    bot.y = 20.0
    bot.vy = -50.0

    from app.game.bots import update_bot

    update_bot(room, bot)

    assert bot.y >= 0.0


def test_corpse_bounces_off_the_ceiling(manager: RoomManager) -> None:
    """죽은 뒤 위로 튄 시체도 천장에서 되돌아온다(계속 올라가면 화면에서 사라진다)."""
    room = _playing_room(manager)
    p = _add_player(room, y=10.0)
    p.hp = 0.0
    p.vy = -30.0

    sim.update_player(room, p)

    assert p.y >= 0.0
    assert p.vy > 0.0, "천장에 부딪혔으면 다시 내려와야 한다"


# --------------------------------------------------------------------------
# 바닥은 그대로 뚫려 있어야 한다
# --------------------------------------------------------------------------


def test_floor_stays_open_so_falling_still_kills(manager: RoomManager) -> None:
    room = _playing_room(manager, map_id="skylands")  # 바닥이 없는 맵
    p = _add_player(room, y=C.HEIGHT + 200)

    assert p.alive
    engine.tick_room(room)
    assert not p.alive, "낙사가 막히면 협곡/부유섬 맵이 성립하지 않는다"


def test_player_is_not_clamped_at_the_bottom(manager: RoomManager) -> None:
    room = _playing_room(manager, map_id="skylands")
    p = _add_player(room, x=400.0, y=C.HEIGHT - 10)
    p.vy = 40.0

    sim.update_player(room, p)

    assert p.y > C.HEIGHT, "바닥에 걸리면 떨어져 죽을 수가 없다"
