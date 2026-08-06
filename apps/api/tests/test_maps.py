"""맵 카탈로그 / 맵 선택 프로토콜 테스트.

맵은 손으로 좌표를 찍어 만든 데이터라 "스폰이 벽 속에 박혀 있다" 같은 실수가 나기 쉽다.
그런 종류의 사고를 자동으로 잡는 것이 이 파일의 목적이다.
"""

from __future__ import annotations

import pytest

from app.game import constants as C
from app.game import engine, maps
from app.game.models import Player
from app.game.rooms import RoomManager


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _add_player(room, pid: str) -> Player:
    p = Player(id=pid, nickname=pid)
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _overlaps(x: float, y: float, w: float, h: float, rect: dict[str, float]) -> bool:
    return (
        x < rect["x"] + rect["width"]
        and x + w > rect["x"]
        and y < rect["y"] + rect["height"]
        and y + h > rect["y"]
    )


# --------------------------------------------------------------------------
# 카탈로그 데이터 검증
# --------------------------------------------------------------------------


def test_catalog_ids_are_unique_and_default_exists() -> None:
    catalog = maps.catalog()
    ids = [m["id"] for m in catalog]
    assert len(ids) == len(set(ids))
    assert maps.DEFAULT_ID in ids
    assert len(ids) >= 5  # 맵 선택이 의미 있으려면 최소한의 가짓수는 있어야 한다
    assert maps.RANDOM_ID not in ids  # "random" 은 실제 맵이 아니다


@pytest.mark.parametrize("game_map", maps.BY_ID.values(), ids=lambda m: m.id)
def test_map_geometry_is_inside_world(game_map: maps.GameMap) -> None:
    assert game_map.platforms, f"{game_map.id}: 발판이 하나도 없다"
    for rect in game_map.platforms:
        assert rect["width"] > 0 and rect["height"] > 0
        assert 0 <= rect["x"] <= C.WIDTH and 0 <= rect["y"] <= C.HEIGHT
        assert rect["x"] + rect["width"] <= C.WIDTH


@pytest.mark.parametrize("game_map", maps.BY_ID.values(), ids=lambda m: m.id)
def test_spawns_are_usable(game_map: maps.GameMap) -> None:
    """스폰 지점이 월드 안에 있고, 발판 안에 파묻혀 있지 않아야 한다."""
    assert len(game_map.spawns) >= 2, f"{game_map.id}: 스폰이 2곳 미만"
    size = C.PLAYER_SIZE
    for x, y in game_map.spawns:
        assert 0 <= x <= C.WIDTH - size, f"{game_map.id}: 스폰 x={x} 가 월드 밖"
        assert 0 <= y <= C.HEIGHT - size, f"{game_map.id}: 스폰 y={y} 가 월드 밖"
        for rect in game_map.platforms:
            assert not _overlaps(x, y, size, size, rect), (
                f"{game_map.id}: 스폰 ({x}, {y}) 이 발판 {rect} 속에 박혀 있다"
            )


@pytest.mark.parametrize("game_map", maps.BY_ID.values(), ids=lambda m: m.id)
def test_map_serializes_for_client(game_map: maps.GameMap) -> None:
    data = game_map.to_dict()
    assert set(data) == {"id", "name", "emoji", "desc", "theme", "platforms", "spawns"}
    assert set(data["theme"]) == {"bg", "grid", "platform", "edge"}
    assert data["name"] and data["desc"]


def test_platforms_are_copied_per_room(manager: RoomManager) -> None:
    """방마다 발판 사본을 가져야 한다(한 방의 변형이 다른 방으로 새면 안 된다)."""
    a = manager.create("pvp", 2, map_id="classic")
    b = manager.create("pvp", 2, map_id="classic")
    a.platforms[0]["x"] = -999.0
    assert b.platforms[0]["x"] == 0.0
    assert maps.get("classic").platforms[0]["x"] == 0.0


# --------------------------------------------------------------------------
# 방 생성 / 선택
# --------------------------------------------------------------------------


def test_create_room_applies_map(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="skylands")
    assert room.map_id == "skylands"
    assert room.active_map_id == "skylands"
    assert len(room.platforms) == len(maps.get("skylands").platforms)


def test_create_room_rejects_unknown_map(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="아무맵")
    assert room.map_id == maps.DEFAULT_ID


def test_training_random_map_avoids_fall_hazards(manager: RoomManager) -> None:
    for _ in range(30):
        room = manager.create("training", 1, map_id=maps.RANDOM_ID)
        assert room.active_map_id in maps.TRAINING_SAFE_IDS


def test_set_map_only_in_waiting(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    assert engine.set_map(room, "arena") is True
    assert room.active_map_id == "arena"

    room.phase = "playing"
    assert engine.set_map(room, "chasm") is False
    assert room.active_map_id == "arena"


def test_set_map_rejects_unknown(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    assert engine.set_map(room, "존재하지-않는-맵") is False
    assert room.map_id == maps.DEFAULT_ID


def test_set_map_random_defers_until_start(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="classic")
    assert engine.set_map(room, maps.RANDOM_ID) is True
    assert room.map_id == maps.RANDOM_ID
    # 아직은 직전 맵이 그대로 깔려 있다가, 시작할 때 실제 맵으로 확정된다.
    _add_player(room, "a")
    _add_player(room, "b")
    assert engine.start_game(room) is True
    assert room.active_map_id in maps.BY_ID


def test_random_selection_rerolls_between_rounds(manager: RoomManager) -> None:
    """무작위를 고르면 ROUNDS 처럼 라운드마다 맵이 바뀐다."""
    room = manager.create("pvp", 2, map_id=maps.RANDOM_ID)
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    seen = {room.active_map_id}
    for _ in range(12):
        engine.reset_round(room)
        seen.add(room.active_map_id)
    assert len(seen) > 1


def test_fixed_selection_never_changes(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="cross")
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)
    for _ in range(8):
        engine.reset_round(room)
        assert room.active_map_id == "cross"


# --------------------------------------------------------------------------
# 스폰 배치
# --------------------------------------------------------------------------


def test_round_start_spreads_players_over_spawns(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="towers")
    a = _add_player(room, "a")
    b = _add_player(room, "b")
    engine.start_game(room)
    assert (a.x, a.y) != (b.x, b.y)
    for p in (a, b):
        assert 0 <= p.x <= C.WIDTH - p.width


def test_round_start_uses_map_spawns(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="skylands")
    player = _add_player(room, "a")
    engine.start_game(room)
    spawns = {(x, y) for x, y in maps.get("skylands").spawns}
    assert (player.x, player.y) in spawns
