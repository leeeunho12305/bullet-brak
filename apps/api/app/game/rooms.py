"""방 저장소. 6자리 코드 발급 / 조회 / 삭제 / 빈 방 정리."""

from __future__ import annotations

import random
import time

from app.game import maps
from app.game.models import Mode, Room

#: 아무도 입장하지 않은 빈 방을 유지해 주는 시간(초)
EMPTY_ROOM_GRACE_SEC = 300.0


class RoomError(RuntimeError):
    """방 생성 실패."""


class RoomManager:
    def __init__(self, max_rooms: int = 200) -> None:
        self.rooms: dict[str, Room] = {}
        self.created_at: dict[str, float] = {}
        self.max_rooms = max_rooms

    # -- 코드 --------------------------------------------------------------
    def _new_code(self) -> str:
        for _ in range(2000):
            code = str(random.randint(100000, 999999))
            if code not in self.rooms:
                return code
        raise RoomError("Could not allocate a room code.")

    # -- CRUD --------------------------------------------------------------
    def create(
        self, mode: Mode = "pvp", max_players: int = 2, map_id: str = maps.DEFAULT_ID
    ) -> Room:
        if len(self.rooms) >= self.max_rooms:
            raise RoomError("The server is full.")
        if not maps.is_valid_selection(map_id):
            map_id = maps.DEFAULT_ID
        room = Room(
            code=self._new_code(),
            mode=mode if mode in ("pvp", "training") else "pvp",
            max_players=max(1, min(8, int(max_players))),
            map_id=map_id,
        )
        resolved = maps.resolve(map_id)
        if room.mode == "training" and map_id == maps.RANDOM_ID:
            # 훈련장 무작위는 낙사 없는 맵에서만 고른다(봇 상대로 떨어지면 연습이 안 된다).
            resolved = random.choice(maps.TRAINING_SAFE_IDS)
        maps.apply(room, resolved)
        if room.mode == "training":
            # 훈련장은 입장 즉시 시작. 웨이브 스폰은 첫 틱에 training 이 처리한다.
            from app.game import training

            room.max_players = 1
            room.phase = "playing"
            training.ensure(room)
        self.rooms[room.code] = room
        self.created_at[room.code] = time.monotonic()
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def remove(self, code: str) -> None:
        self.rooms.pop(code, None)
        self.created_at.pop(code, None)
        # 라운드 승자 캐시도 함께 정리(순환 import 방지를 위해 지연 import)
        from app.game import engine

        engine.forget_room(code)

    # -- 정리 --------------------------------------------------------------
    def is_full(self, room: Room) -> bool:
        return len(room.players) >= room.max_players

    def cleanup_empty(self, grace_sec: float = EMPTY_ROOM_GRACE_SEC) -> list[str]:
        """생성 후 grace_sec 이 지나도록 비어 있는 방을 삭제하고 코드 목록을 반환."""
        now = time.monotonic()
        empty = [
            code
            for code, room in self.rooms.items()
            if not room.players and now - self.created_at.get(code, 0.0) > grace_sec
        ]
        for code in empty:
            self.remove(code)
        return empty

    def __len__(self) -> int:
        return len(self.rooms)


#: 프로세스 전역 싱글턴(REST/WS/틱 루프가 공유)
room_manager = RoomManager()
