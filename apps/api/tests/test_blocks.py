"""블럭(점프대 / 이동발판 / 빙판 / 가시)과 맵 에디터 테스트.

블럭은 손으로 찍은 좌표와 물리가 맞물리는 부분이라 "점프대가 목표 높이까지 못 닿는다"
같은 실수가 조용히 지나가기 쉽다. 그런 종류의 사고를 잡는 것이 이 파일의 목적이다.
"""

from __future__ import annotations

import pytest

from app.game import blocks, constants as C
from app.game import engine, maps
from app.game.models import Player, Room
from app.game.rooms import RoomManager


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _add_player(room: Room, pid: str) -> Player:
    p = Player(id=pid, nickname=pid)
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _run(room: Room, ticks: int) -> None:
    for _ in range(ticks):
        engine.tick_room(room)


def _min_y(room: Room, player: Player, ticks: int) -> float:
    """플레이어를 ticks 만큼 굴리면서 도달한 가장 높은 지점(y 최솟값)."""
    best = player.y
    for _ in range(ticks):
        engine.tick_room(room)
        best = min(best, player.y)
    return best


# --------------------------------------------------------------------------
# 블럭 데이터
# --------------------------------------------------------------------------


def test_plain_rect_is_solid() -> None:
    assert maps.rect(0, 0, 10, 10)["type"] == blocks.SOLID


def test_snap_hides_internal_fields() -> None:
    """스냅샷에는 서버 내부 계산용 필드(ox/oy/dx/dy)가 새지 않아야 한다."""
    block = maps.mover(400, 300, 100)
    block["dx"] = 3.0
    out = blocks.snap(block)
    assert set(out) == {"x", "y", "width", "height", "type", "axis"}


def test_full_snap_round_trips_through_the_editor() -> None:
    """대기실 payload 는 이동발판 설정까지 실어야 한다 — 다시 저장해도 값이 살아남는다."""
    original = maps.mover(400, 300, 100, axis="y", span=250, speed=2.4)
    original["x"] = 480.0  # 왕복 중이라 지금 위치가 원점에서 벗어나 있다

    sent = blocks.snap(original, full=True)
    assert sent["span"] == 250 and sent["speed"] == 2.4
    assert sent["x"] == 400.0, "지금 위치가 아니라 왕복의 중심을 보내야 한다"

    back = blocks.normalize(sent)
    assert back is not None
    assert (back["span"], back["speed"], back["axis"]) == (250.0, 2.4, "y")
    assert (back["ox"], back["oy"]) == (400.0, 300.0)


def test_normalize_rejects_junk_and_clamps_to_world() -> None:
    assert blocks.normalize("발판") is None
    assert blocks.normalize({"x": "a", "y": None, "width": 0, "height": -5}) is not None

    block = blocks.normalize({"x": 9999, "y": -50, "width": 5, "height": 99999, "type": "우주"})
    assert block is not None
    assert block["type"] == blocks.SOLID  # 모르는 종류는 일반 블럭으로
    assert block["width"] == blocks.MIN_SIZE
    assert block["height"] == C.HEIGHT
    assert 0 <= block["x"] <= C.WIDTH - block["width"]
    assert block["y"] == 0.0


def test_normalize_all_caps_block_count() -> None:
    raw = [{"x": 0, "y": 0, "width": 20, "height": 20}] * (blocks.MAX_BLOCKS + 20)
    assert len(blocks.normalize_all(raw)) == blocks.MAX_BLOCKS
    assert blocks.normalize_all("발판들") == []


# --------------------------------------------------------------------------
# 점프대
# --------------------------------------------------------------------------


def test_jump_pad_launches_higher_than_a_normal_jump(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.rect(0, 550, 800, 50), maps.jump(300, 534, 100)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 330.0, 480.0
    player.vx = player.vy = 0.0
    top = _min_y(room, player, 120)

    # 제자리 점프(JUMP_POWER=-16)로 오르는 높이보다 확실히 위로 올라간다.
    plain_jump_height = C.JUMP_POWER**2 / (2 * C.GRAVITY)
    assert 534 - top > plain_jump_height * 1.3


def test_towers_pit_has_a_way_back_up(manager: RoomManager) -> None:
    """쌍둥이 탑: 탑 사이 바닥에 떨어져도 점프대로 다리 높이까지 되돌아갈 수 있다."""
    room = manager.create("pvp", 2, map_id="towers")
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    pads = [p for p in room.platforms if p["type"] == blocks.JUMP]
    assert pads, "탑 사이에 복귀용 점프대가 없다"

    bridge_y = 300.0  # 두 탑을 잇는 다리
    for pad in pads:
        player = room.players["a"]
        player.x = pad["x"] + 5
        player.y = pad["y"] - player.height - 20
        player.vx = player.vy = 0.0
        top = _min_y(room, player, 150)
        assert top < bridge_y, f"점프대 {pad['x']} 에서 다리(y={bridge_y})까지 못 올라간다"


def test_jump_pad_refills_air_jumps(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.rect(0, 550, 800, 50), maps.jump(300, 534, 100)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 330.0, 480.0
    player.vx = player.vy = 0.0
    player.jumps = 5
    _run(room, 20)
    assert player.jumps == 0


# --------------------------------------------------------------------------
# 이동발판
# --------------------------------------------------------------------------


def test_mover_oscillates_around_its_origin(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.mover(400, 300, 100, axis="x", span=100, speed=2.0)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    seen = []
    for _ in range(400):
        engine.tick_room(room)
        seen.append(room.platforms[0]["x"])
    assert max(seen) > 460 and min(seen) < 340  # 양쪽 끝까지 왕복한다
    assert all(300 <= x <= 500 for x in seen)  # span 을 넘어가지는 않는다


def test_mover_carries_the_rider(manager: RoomManager) -> None:
    """올라탄 사람은 발판과 함께 움직인다(제자리에 남겨지면 안 된다)."""
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.mover(400, 300, 140, axis="x", span=150, speed=1.5)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 430.0, 250.0
    player.vx = player.vy = 0.0
    _run(room, 10)  # 발판 위에 내려앉는다
    assert player.ride == 0

    offset = player.x - room.platforms[0]["x"]
    for _ in range(90):
        engine.tick_room(room)
        if player.ride < 0:  # 발판에서 떨어졌으면 검사를 멈춘다
            break
        assert abs((player.x - room.platforms[0]["x"]) - offset) < 6.0


def test_mover_position_survives_a_round_reset(manager: RoomManager) -> None:
    """라운드가 다시 시작돼도 이동발판이 원점에서 이어져야 한다(누적 드리프트 금지)."""
    room = manager.create("pvp", 2, map_id="factory")
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)
    _run(room, 200)
    engine.reset_round(room)
    _run(room, 200)

    for now, original in zip(room.platforms, maps.get("factory").platforms):
        if original["type"] != blocks.MOVER:
            continue
        assert abs(now["x"] - original["ox"]) <= original["span"] + 1
        assert abs(now["y"] - original["oy"]) <= original["span"] + 1


# --------------------------------------------------------------------------
# 빙판 / 가시
# --------------------------------------------------------------------------


def _slide(manager: RoomManager, ground: dict) -> tuple[float, Player]:
    """바닥 위에 세운 플레이어를 오른쪽으로 밀고, 입력 없이 40틱 미끄러진 거리를 잰다."""
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [ground])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x = 100.0
    player.y = ground["y"] - player.height  # 공중에서 시작하면 낙하 중 마찰이 먼저 먹는다
    # 이동 속도 상한으로 민다. 리터럴을 쓰면 PLAYER_SPEED 를 낮췄을 때 초과분이
    # 넉백으로 취급돼(sim 의 KNOCKBACK_DECAY) 마찰 대신 천천히 식는다.
    player.vx, player.vy = C.PLAYER_SPEED, 0.0
    _run(room, 40)
    return player.x - 100.0, player


def test_ice_keeps_you_sliding(manager: RoomManager) -> None:
    on_ice, player = _slide(manager, maps.ice(0, 550, 800, 50))
    on_solid, _ = _slide(manager, maps.rect(0, 550, 800, 50))

    assert player.on_ice
    assert on_solid < 25.0, "일반 블럭인데 미끄러졌다"
    assert on_ice > on_solid * 4, f"빙판({on_ice:.0f}px)이 일반 블럭({on_solid:.0f}px)만큼밖에 안 미끄럽다"


def test_spikes_hurt_and_bounce(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.spike(0, 550, 800, 50)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 100.0, 500.0
    player.vx = player.vy = 0.0
    before = player.hp
    _run(room, 30)
    assert player.hp < before
    assert player.y < 520, "가시를 밟았는데 튕겨나지 않았다"


def test_spikes_cost_a_flat_50_per_step(manager: RoomManager) -> None:
    """가시는 밟을 때마다 50 이다 — 닿아 있는 동안 조금씩 갈리는 게 아니다."""
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.spike(0, 550, 800, 50)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 100.0, 500.0
    player.vx = player.vy = 0.0
    before = player.hp

    # 튕겨 오르고 다시 떨어지기 전까지는 한 번만 깎인다.
    _run(room, 20)
    assert before - player.hp == pytest.approx(blocks.HAZARD_DAMAGE)

    # 무적 시간이 지나고 다시 밟으면 또 한 번.
    _run(room, blocks.HAZARD_GRACE + 30)
    assert before - player.hp == pytest.approx(blocks.HAZARD_DAMAGE * 2)


def test_spawn_points_never_land_on_spikes(manager: RoomManager) -> None:
    """가시 위에 스폰되면 시작하자마자 50 을 잃는다 — 맵이든 에디터 배치든 막는다."""
    room = manager.create("pvp", 2, map_id="factory")
    for x, y in maps.spawn_points(room):
        assert maps._landing_kind(room.platforms, x, y) != blocks.HAZARD

    # 에디터로 바닥 전체를 가시로 덮고 한쪽만 안전하게 남겨도 그쪽으로 밀려나야 한다.
    engine.set_platforms(
        room, [maps.spike(0, 550, 620, 50), maps.rect(620, 550, 180, 50)]
    )
    for x, y in maps.spawn_points(room):
        assert maps._landing_kind(room.platforms, x, y) != blocks.HAZARD


# --------------------------------------------------------------------------
# 바닥에 박아 넣는 점프대
# --------------------------------------------------------------------------


def test_flush_jump_pad_does_not_block_the_walk(manager: RoomManager) -> None:
    """바닥과 같은 높이의 점프대는 옆면이 없다 — 달려오다 걸려 멈추면 안 된다."""
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.rect(0, 550, 800, 50), maps.jump(400, 550, 100)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 300.0, 520.0
    player.vx = player.vy = 0.0
    player.inputs.right = True

    launched = False
    for _ in range(60):
        engine.tick_room(room)
        launched = launched or player.vy < -10
    assert player.x > 420.0, "점프대에 걸려 앞으로 나아가지 못했다"
    assert launched, "점프대 위를 지나갔는데 튀어오르지 않았다"


def test_flush_jump_pad_launches_a_walker(manager: RoomManager) -> None:
    """바닥에 박힌 점프대 위에 서 있기만 해도 튀어오른다."""
    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.rect(0, 550, 800, 50), maps.jump(300, 550, 100)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    player = room.players["a"]
    player.x, player.y = 330.0, 520.0
    player.vx = player.vy = 0.0
    top = _min_y(room, player, 120)

    plain_jump_height = C.JUMP_POWER**2 / (2 * C.GRAVITY)
    assert 520 - top > plain_jump_height * 1.3


def test_bullets_pass_through_jump_pads(manager: RoomManager) -> None:
    """점프대는 실체가 없다 — 탄환도 걸리지 않는다."""
    from app.game.bullets import spawn_bullet

    room = manager.create("pvp", 2)
    engine.set_platforms(room, [maps.jump(300, 300, 200, 40)])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    shooter = room.players["a"]
    shooter.x, shooter.y = 100.0, 300.0
    room.bullets.append(spawn_bullet(room, shooter, 0.0))
    _run(room, 30)
    assert room.bullets and room.bullets[0].x > 500.0


# --------------------------------------------------------------------------
# 맵 에디터 (set_platforms)
# --------------------------------------------------------------------------


def test_set_platforms_applies_and_pins_the_map(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id=maps.RANDOM_ID)
    layout = [
        {"x": 0, "y": 560, "width": 800, "height": 40},
        {"x": 300, "y": 400, "width": 120, "height": 16, "type": "jump", "power": 20},
    ]
    assert engine.set_platforms(room, layout) is True
    assert room.custom_layout is not None
    assert len(room.platforms) == 2
    assert room.platforms[1]["type"] == blocks.JUMP
    # 편집하면 "무작위"가 풀리고 지금 맵으로 고정된다.
    assert room.map_id == room.active_map_id


def test_custom_layout_survives_round_resets(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="classic")
    engine.set_platforms(room, [{"x": 0, "y": 560, "width": 800, "height": 40}])
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)
    for _ in range(3):
        engine.reset_round(room)
        assert len(room.platforms) == 1


def test_set_platforms_rejected_mid_game(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    assert engine.set_platforms(room, [{"x": 0, "y": 0, "width": 50, "height": 50}]) is False
    assert room.custom_layout is None


def test_set_platforms_rejects_empty_layout(manager: RoomManager) -> None:
    """전부 지운 배치는 받지 않는다(발판이 없으면 시작하자마자 전원 낙사한다)."""
    room = manager.create("pvp", 2)
    assert engine.set_platforms(room, []) is False
    assert engine.set_platforms(room, ["쓰레기", 42]) is False
    assert room.custom_layout is None


def test_reset_and_set_map_restore_the_original_terrain(manager: RoomManager) -> None:
    room = manager.create("pvp", 2, map_id="classic")
    original = len(room.platforms)

    engine.set_platforms(room, [{"x": 0, "y": 560, "width": 800, "height": 40}])
    assert engine.clear_platforms(room) is True
    assert room.custom_layout is None
    assert len(room.platforms) == original

    engine.set_platforms(room, [{"x": 0, "y": 560, "width": 800, "height": 40}])
    engine.set_map(room, "arena")
    assert room.custom_layout is None
    assert len(room.platforms) == len(maps.get("arena").platforms)


def test_room_state_shows_the_edited_layout(manager: RoomManager) -> None:
    from app.game.serialize import room_state

    room = manager.create("pvp", 2, map_id="classic")
    assert room_state(room)["custom_map"] is False

    engine.set_platforms(room, [{"x": 0, "y": 560, "width": 800, "height": 40}])
    state = room_state(room)
    assert state["custom_map"] is True
    assert len(state["map"]["platforms"]) == 1
