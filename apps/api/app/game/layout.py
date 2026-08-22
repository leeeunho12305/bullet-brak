"""방의 맵과 스폰 배치 — 고르기 / 편집 / 라운드 시작 전 확정.

`engine` 에서 떼어낸 조각이다(파일당 400줄). 호출부는 예전처럼 `engine.set_map(...)`
을 그대로 쓰면 된다 — engine 이 이 모듈의 함수를 다시 내보낸다(PROTOCOL §5 계약 유지).

FastAPI/WebSocket 을 import 하지 않는다(순수 로직).
"""

from __future__ import annotations

import random
from typing import Any

from app.game import blocks, constants as C
from app.game import maps
from app.game.models import Room
from app.game.physics import clamp

#: 맵과 지형을 바꿀 수 있는 페이즈. 전투 중에 발판이 사라지면 그 라운드가 무효가 된다.
EDITABLE_PHASES = ("waiting", "finished")


def random_spawn(room: Room | None = None) -> tuple[float, float]:
    """맵에 정의된 스폰 지점 하나. 맵을 모르면 월드 상단 랜덤."""
    points = maps.spawn_points(room)
    return random.choice(points) if points else maps.fallback_spawn()


def place_players(room: Room) -> None:
    """라운드 시작 배치. 스폰 지점을 섞어 겹치지 않게 나눠 준다."""
    points = maps.spawn_points(room)
    random.shuffle(points)
    for i, p in enumerate(room.players.values()):
        if not points:
            x, y = maps.fallback_spawn()
        else:
            x, y = points[i % len(points)]
            if i >= len(points):  # 스폰 지점보다 사람이 많으면 자리를 재사용하므로 흩뜨린다
                x += random.uniform(-45.0, 45.0)
        p.x = clamp(x, 0.0, C.WIDTH - p.width)
        p.y = y


def prepare_map(room: Room) -> None:
    """라운드 시작 전 맵 확정.

    방장이 "무작위"를 골랐다면 ROUNDS 처럼 라운드마다 새 맵을 뽑는다.
    훈련장은 낙사 없는 맵에서만 고른다(봇 상대로 떨어지면 연습이 안 된다).
    """
    if room.map_id == maps.RANDOM_ID:
        pool = maps.TRAINING_SAFE_IDS if room.mode == "training" else None
        maps.apply(room, maps.random_id(exclude=room.active_map_id, pool=pool))
    elif room.active_map_id != room.map_id:
        maps.apply(room, room.map_id)


def _locked(room: Room) -> bool:
    """지금 이 방의 지형을 건드릴 수 없는가.

    경쟁전은 언제나 잠겨 있다 — 방장이 자기가 잘하는 맵을 골라 놓거나 지형을 짜 놓고
    시작하면 그 판은 이미 같은 조건의 경기가 아니다. 경쟁전 맵은 라운드마다 무작위다.
    """
    return room.ranked or room.phase not in EDITABLE_PHASES


def set_map(room: Room, map_id: str) -> bool:
    """방장의 맵 선택. 대기실 / 매치 종료 상태에서만 바꿀 수 있다.

    맵을 다시 고르면 에디터로 짠 배치는 버린다(고른 맵의 원본 지형으로 돌아간다).
    """
    if _locked(room) or not maps.is_valid_selection(map_id):
        return False
    room.map_id = map_id
    room.custom_layout = None
    if map_id != maps.RANDOM_ID:
        maps.apply(room, map_id)
    else:
        maps.apply(room, room.active_map_id)  # 원본 지형 복구(미리보기용)
    return True


def set_platforms(room: Room, raw: Any) -> bool:
    """방장이 맵 에디터에서 저장한 배치를 방에 적용한다.

    편집한 순간 맵은 지금 깔린 맵으로 고정된다 — "무작위"인 채로 두면 다음 라운드에
    남의 맵 위에 내 배치가 얹혀서 뜻이 통하지 않는다.
    """
    if _locked(room):
        return False
    layout = blocks.normalize_all(raw)
    if not layout:
        return False
    room.custom_layout = layout
    room.map_id = room.active_map_id
    maps.apply(room, room.active_map_id)
    return True


def clear_platforms(room: Room) -> bool:
    """맵 에디터 초기화. 지금 맵의 원본 지형으로 되돌린다."""
    if _locked(room):
        return False
    room.custom_layout = None
    maps.apply(room, room.active_map_id)
    return True
