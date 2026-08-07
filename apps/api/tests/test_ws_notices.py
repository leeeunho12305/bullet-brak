"""WebSocket 알림 계약 테스트 (player_left / 리매치 표 집계).

둘 다 "화면에 무엇이 뜨는가"를 결정하는 메시지라, 필드 이름이 바뀌면 클라이언트가
조용히 아무것도 안 보여주게 된다. 그래서 로직이 아니라 메시지 자체를 검사한다.

주의: TestClient 는 lifespan 을 돌리지 않으므로 60Hz 틱 루프가 없다.
      즉 메시지는 핸들러가 직접 보내는 것뿐이고, "안 오는 메시지"를 receive 로
      기다리면 영원히 멈춘다. 방송이 없는 경로는 상태를 폴링해서 확인한다.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.game.models import Room
from app.game.rooms import room_manager
from app.game.serialize import snapshot
from app.main import create_app

#: 핸들러가 다른 스레드에서 처리하므로 상태 반영까지 잠깐 기다린다.
SETTLE_TIMEOUT_SEC = 2.0


@pytest.fixture
def client() -> TestClient:
    room_manager.rooms.clear()
    room_manager.created_at.clear()
    return TestClient(create_app())


def _join(ws: Any, nickname: str) -> dict[str, Any]:
    ws.send_json({"type": "join", "nickname": nickname})
    return ws.receive_json()


def _new_room(client: TestClient, **body: Any) -> str:
    payload = {"mode": "pvp", "max_players": 2, **body}
    return str(client.post("/api/rooms", json=payload).json()["code"])


def _await_message(ws: Any, msg_type: str, limit: int = 40) -> dict[str, Any] | None:
    """그 타입의 메시지가 **새로** 온다고 확신할 때만 쓴다(오지 않으면 블록된다).

    room_state 처럼 입장·시작 때마다 오는 타입은 이미 큐에 쌓여 있어서, 이걸로 기다리면
    옛 메시지를 집고 곧바로 돌아온다. 그런 경우엔 _await_state 를 써라.
    """
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("type") == msg_type:
            return msg
    return None


def _await_state(check: Callable[[], bool], what: str) -> None:
    """서버가 다른 스레드에서 처리하므로, 방 상태가 조건을 만족할 때까지 폴링한다."""
    deadline = time.monotonic() + SETTLE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.01)
    raise AssertionError(f"{what} — 제한 시간 안에 이뤄지지 않았다")


def _await_votes(room: Room, count: int) -> None:
    """리매치 투표는 pending 이면 방송이 없다 — 상태를 폴링한다."""
    _await_state(lambda: len(room.rematch_votes) >= count, f"리매치 표 {count}개")


# --------------------------------------------------------------------------
# 상대 이탈 알림
# --------------------------------------------------------------------------


def test_player_left_reaches_the_remaining_player(client: TestClient) -> None:
    code = _new_room(client)

    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            _join(guest, "게스트")
        # guest 소켓이 닫혔다 → 남은 host 에게 알림이 가야 한다
        notice = _await_message(host, "player_left")

    assert notice is not None, "상대가 나갔는데 player_left 가 오지 않았다"
    assert set(notice) == {"type", "player_id", "nickname", "players_left"}
    assert notice["nickname"] == "게스트"
    assert notice["players_left"] == 1


def test_player_left_carries_the_nickname_not_the_id(client: TestClient) -> None:
    """배너에 닉네임을 그대로 쓰므로 빈 값이면 안 된다."""
    code = _new_room(client)
    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            welcome = _join(guest, "")  # 빈 닉네임 → 서버가 기본값을 넣는다
        notice = _await_message(host, "player_left")

    assert notice is not None
    assert notice["player_id"] == welcome["player_id"]
    assert notice["nickname"], "닉네임이 비어 있으면 배너가 '  님이 나갔습니다' 가 된다"


def test_room_disappears_when_the_last_player_leaves(client: TestClient) -> None:
    """마지막 한 명이 나가면 방이 사라진다 — 알림을 보낼 상대도 없다."""
    code = _new_room(client)
    with client.websocket_connect(f"/ws/{code}") as solo:
        _join(solo, "혼자")
    assert room_manager.get(code) is None


def test_match_is_reset_when_the_opponent_leaves(client: TestClient) -> None:
    """상대가 나가면 남은 사람은 대기실로 돌아간다(그래서 알림이 필요하다)."""
    code = _new_room(client)
    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            _join(guest, "게스트")
            host.send_json({"type": "start_game"})
            room = room_manager.get(code)
            assert room is not None
            _await_state(lambda: room.phase == "playing", "게임 시작")
        # 이 시점에 guest 만 나갔다. host 까지 나가면 방이 통째로 사라지므로 안에서 검사한다.
        _await_message(host, "player_left")
        assert room.phase == "waiting"
        assert len(room.players) == 1


# --------------------------------------------------------------------------
# 리매치 표 (오버레이의 "1/2")
# --------------------------------------------------------------------------


def test_one_vote_shows_up_as_one_of_two(client: TestClient) -> None:
    code = _new_room(client)

    with client.websocket_connect(f"/ws/{code}") as host:
        welcome = _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            _join(guest, "게스트")
            room = room_manager.get(code)
            assert room is not None
            room.phase = "finished"
            room.winner_id = welcome["player_id"]

            host.send_json({"type": "rematch", "accept": True})
            _await_votes(room, 1)

            snap = snapshot(room)
            assert snap["rematch"] == [welcome["player_id"]]  # 분자
            assert len(snap["players"]) == 2  # 분모
            assert room.phase == "finished", "혼자 눌렀으면 아직 기다려야 한다"


def test_both_votes_start_the_next_match(client: TestClient) -> None:
    code = _new_room(client)

    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            _join(guest, "게스트")
            room = room_manager.get(code)
            assert room is not None
            room.phase = "finished"

            host.send_json({"type": "rematch", "accept": True})
            _await_votes(room, 1)
            guest.send_json({"type": "rematch", "accept": True})
            _await_state(lambda: room.phase == "playing", "양쪽 동의 후 새 매치 시작")

            assert room.rematch_votes == set()


def test_leaving_clears_that_players_rematch_vote(client: TestClient) -> None:
    code = _new_room(client)

    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            guest_welcome = _join(guest, "게스트")
            room = room_manager.get(code)
            assert room is not None
            room.phase = "finished"

            guest.send_json({"type": "rematch", "accept": True})
            _await_votes(room, 1)
            assert room.rematch_votes == {guest_welcome["player_id"]}

        _await_message(host, "player_left")
        assert room.rematch_votes == set(), "나간 사람의 표가 남으면 다음 매치가 혼자 시작된다"
        assert list(room.players) != [guest_welcome["player_id"]]


# --------------------------------------------------------------------------
# 맵 에디터 (set_platforms / reset_platforms)
# --------------------------------------------------------------------------

_LAYOUT = [
    {"x": 0, "y": 560, "width": 800, "height": 40},
    {"x": 300, "y": 400, "width": 120, "height": 16, "type": "jump", "power": 20},
]


def test_host_can_edit_the_map_layout(client: TestClient) -> None:
    code = _new_room(client)
    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        host.send_json({"type": "set_platforms", "platforms": _LAYOUT})
        room = room_manager.get(code)
        assert room is not None
        _await_state(lambda: room.custom_layout is not None, "배치 저장")

        # 입장 때 온 room_state 가 이미 큐에 있으므로, 편집이 반영된 것이 나올 때까지 넘긴다.
        state = None
        for _ in range(10):
            msg = _await_message(host, "room_state")
            if msg is not None and msg["room"]["custom_map"]:
                state = msg
                break
        assert state is not None, "편집 결과가 담긴 room_state 가 오지 않았다"
        # 대기실 미리보기가 편집 결과를 그대로 보여줘야 한다.
        platforms = state["room"]["map"]["platforms"]
        assert len(platforms) == 2
        assert platforms[1]["type"] == "jump"

        host.send_json({"type": "reset_platforms"})
        _await_state(lambda: room.custom_layout is None, "원본 지형 복구")


def test_guest_cannot_edit_the_map_layout(client: TestClient) -> None:
    """맵 에디터는 방장 전용 — 게스트 요청은 조용히 무시된다."""
    code = _new_room(client)
    with client.websocket_connect(f"/ws/{code}") as host:
        _join(host, "호스트")
        with client.websocket_connect(f"/ws/{code}") as guest:
            _join(guest, "게스트")
            room = room_manager.get(code)
            assert room is not None
            before = len(room.platforms)

            guest.send_json({"type": "set_platforms", "platforms": _LAYOUT})
            # 무시되므로 방송이 없다 — 상태를 폴링해서 "안 바뀌었음"을 확인한다.
            time.sleep(0.2)
            assert room.custom_layout is None
            assert len(room.platforms) == before
