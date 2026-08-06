"""맵 카탈로그. 발판 배치 / 스폰 지점 / 색 테마를 한곳에 모은다.

방장이 대기실에서 고르고(`set_map`), 게임 시작 시 방에 적용된다(`apply`).
constants 외에는 아무것도 import 하지 않는다(순수 데이터 — models 가 이 모듈을 쓴다).

발판은 모두 실체가 있는 AABB 다(위/아래/옆 전부 막힌다). 설계 기준:
  - 플레이어 30x30, 점프 최고 높이 ≈ 213px, 점프 한 번의 수평 도달 ≈ 265px
  - 그러므로 수직 단차는 150px 이하, 건너뛰는 틈은 200px 이하로 둔다
  - 바닥이 없는 구간은 낙사(y > HEIGHT+100)로 이어진다 — 의도된 위험이다
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.game import constants as C

if TYPE_CHECKING:  # 순환 import 방지 (런타임에는 필요 없음)
    from app.game.models import Room

Rect = dict[str, float]

#: 방장이 "무작위"를 골랐을 때 쓰는 특수 id. 실제 맵이 아니다.
RANDOM_ID = "random"


def rect(x: float, y: float, width: float, height: float) -> Rect:
    return {"x": float(x), "y": float(y), "width": float(width), "height": float(height)}


@dataclass(frozen=True)
class Theme:
    """캔버스 배경/발판 색. 클라이언트 renderer 가 그대로 받아 쓴다."""

    bg: str
    grid: str
    platform: str
    edge: str

    def to_dict(self) -> dict[str, str]:
        return {"bg": self.bg, "grid": self.grid, "platform": self.platform, "edge": self.edge}


@dataclass(frozen=True)
class GameMap:
    id: str
    name: str
    emoji: str
    desc: str
    theme: Theme
    platforms: tuple[Rect, ...]
    #: 라운드 시작 위치. 플레이어 수만큼 앞에서부터 나눠 준다.
    spawns: tuple[tuple[float, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "desc": self.desc,
            "theme": self.theme.to_dict(),
            "platforms": [dict(p) for p in self.platforms],
            "spawns": [{"x": x, "y": y} for x, y in self.spawns],
        }


# --------------------------------------------------------------------------
# 카탈로그
# --------------------------------------------------------------------------

_MAPS: tuple[GameMap, ...] = (
    GameMap(
        id="classic",
        name="클래식",
        emoji="🟦",
        desc="넓은 바닥과 3단 발판. 기본기를 겨루는 표준 맵.",
        theme=Theme("#0b0d17", "rgba(0, 229, 255, 0.055)", "#1b2438", "rgba(0, 229, 255, 0.45)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(100, 400, 200, 20),
            rect(500, 400, 200, 20),
            rect(300, 250, 200, 20),
        ),
        spawns=((100, 150), (670, 150), (380, 120), (200, 320)),
    ),
    GameMap(
        id="towers",
        name="쌍둥이 탑",
        emoji="🏙️",
        desc="양쪽 탑과 연결 다리. 높이 싸움이 전부다.",
        theme=Theme("#0d0a1c", "rgba(177, 151, 252, 0.07)", "#241d3d", "rgba(177, 151, 252, 0.5)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(140, 330, 60, 220),
            rect(600, 330, 60, 220),
            rect(260, 300, 280, 20),
            rect(50, 190, 160, 20),
            rect(590, 190, 160, 20),
        ),
        spawns=((70, 120), (680, 120), (390, 200), (390, 60)),
    ),
    GameMap(
        id="chasm",
        name="협곡",
        emoji="🌋",
        desc="한가운데가 뚫려 있다. 발을 헛디디면 그대로 낙사.",
        theme=Theme("#160a0a", "rgba(255, 143, 77, 0.06)", "#33201a", "rgba(255, 143, 77, 0.5)"),
        platforms=(
            rect(0, 520, 300, 80),
            rect(500, 520, 300, 80),
            rect(370, 430, 60, 40),
            rect(60, 360, 180, 20),
            rect(560, 360, 180, 20),
            rect(330, 250, 140, 20),
        ),
        spawns=((110, 300), (640, 300), (380, 150), (170, 180)),
    ),
    GameMap(
        id="stairs",
        name="계단",
        emoji="🪜",
        desc="왼쪽 아래에서 오른쪽 위로. 고지를 먼저 잡는 쪽이 유리하다.",
        theme=Theme("#0a1410", "rgba(148, 216, 45, 0.06)", "#18291c", "rgba(148, 216, 45, 0.45)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(0, 470, 180, 20),
            rect(180, 400, 160, 20),
            rect(340, 330, 160, 20),
            rect(500, 260, 160, 20),
            rect(660, 190, 140, 20),
            rect(120, 240, 150, 20),
        ),
        spawns=((60, 380), (700, 100), (380, 240), (250, 150)),
    ),
    GameMap(
        id="arena",
        name="투기장",
        emoji="🏟️",
        desc="양옆이 벽으로 막힌 좁은 무대. 도망칠 곳이 없다.",
        theme=Theme("#150f06", "rgba(255, 212, 59, 0.06)", "#2e2412", "rgba(255, 212, 59, 0.45)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(0, 300, 40, 250),
            rect(760, 300, 40, 250),
            rect(300, 420, 200, 20),
            rect(90, 300, 150, 20),
            rect(560, 300, 150, 20),
            rect(330, 180, 140, 20),
        ),
        spawns=((110, 200), (650, 200), (390, 330), (390, 90)),
    ),
    GameMap(
        id="skylands",
        name="부유섬",
        emoji="☁️",
        desc="바닥이 없다. 섬과 섬 사이는 전부 허공.",
        theme=Theme("#04101f", "rgba(77, 171, 247, 0.07)", "#12263f", "rgba(77, 171, 247, 0.55)"),
        platforms=(
            rect(280, 420, 240, 24),
            rect(60, 340, 160, 22),
            rect(580, 340, 160, 22),
            rect(150, 200, 140, 20),
            rect(510, 200, 140, 20),
            rect(40, 520, 120, 20),
            rect(640, 520, 120, 20),
        ),
        spawns=((330, 340), (450, 340), (110, 250), (630, 250)),
    ),
    GameMap(
        id="bunker",
        name="벙커",
        emoji="🛡️",
        desc="가운데 엄폐 구조물. 옆구리로만 드나들 수 있다.",
        theme=Theme("#0e1114", "rgba(173, 181, 189, 0.06)", "#232a31", "rgba(173, 181, 189, 0.45)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(260, 380, 280, 20),
            rect(260, 400, 20, 90),
            rect(520, 400, 20, 90),
            rect(40, 300, 180, 20),
            rect(580, 300, 180, 20),
            rect(340, 230, 120, 20),
        ),
        spawns=((90, 200), (690, 200), (395, 300), (395, 130)),
    ),
    GameMap(
        id="cross",
        name="십자로",
        emoji="✚",
        desc="가운데 벽이 시야를 끊는다. 정면 대결은 통하지 않는다.",
        theme=Theme("#14060d", "rgba(255, 46, 151, 0.06)", "#2c1120", "rgba(255, 46, 151, 0.5)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(370, 220, 60, 330),
            rect(180, 380, 440, 24),
            rect(30, 280, 140, 20),
            rect(630, 280, 140, 20),
            rect(300, 140, 200, 20),
        ),
        spawns=((110, 190), (680, 190), (250, 300), (550, 300)),
    ),
    GameMap(
        id="rooftop",
        name="옥상",
        emoji="🌃",
        desc="건물 두 채와 하늘다리. 아래로 떨어져도 죽지는 않는다.",
        theme=Theme("#081413", "rgba(32, 201, 151, 0.06)", "#14302b", "rgba(32, 201, 151, 0.5)"),
        platforms=(
            rect(0, 560, 800, 40),
            rect(60, 380, 200, 180),
            rect(540, 380, 200, 180),
            rect(100, 240, 120, 18),
            rect(580, 240, 120, 18),
            rect(300, 300, 200, 18),
            rect(330, 470, 140, 18),
        ),
        spawns=((150, 300), (650, 300), (400, 210), (400, 380)),
    ),
)

BY_ID: dict[str, GameMap] = {m.id: m for m in _MAPS}
DEFAULT_ID = "classic"

#: 낙사 위험이 없는 맵(훈련장은 여기서만 고른다 — 봇을 상대하다 떨어지면 학습이 안 된다)
TRAINING_SAFE_IDS = ("classic", "stairs", "arena", "bunker", "cross")


# --------------------------------------------------------------------------
# 조회 / 적용
# --------------------------------------------------------------------------


def get(map_id: str | None) -> GameMap:
    """id 로 맵을 얻는다. 모르는 id 면 기본 맵."""
    return BY_ID.get(str(map_id or ""), BY_ID[DEFAULT_ID])


def is_valid_selection(map_id: str) -> bool:
    """방장이 고를 수 있는 값인가(실제 맵 id 이거나 "random")."""
    return map_id == RANDOM_ID or map_id in BY_ID


def catalog() -> list[dict[str, Any]]:
    """REST `/api/maps` 응답."""
    return [m.to_dict() for m in _MAPS]


def platforms_of(map_id: str | None) -> list[Rect]:
    """방에 넣을 수 있는 발판 사본(방마다 독립적이어야 한다)."""
    return [dict(p) for p in get(map_id).platforms]


def random_id(exclude: str | None = None, pool: tuple[str, ...] | None = None) -> str:
    """무작위 맵 id. 직전 맵은 되도록 피한다. pool 로 후보를 좁힐 수 있다."""
    candidates = list(pool) if pool else [m.id for m in _MAPS]
    candidates = [mid for mid in candidates if mid in BY_ID]
    if not candidates:
        return DEFAULT_ID
    narrowed = [mid for mid in candidates if mid != exclude] or candidates
    return random.choice(narrowed)


def resolve(map_id: str, current: str | None = None) -> str:
    """선택값을 실제 맵 id 로 바꾼다("random" → 무작위)."""
    if map_id == RANDOM_ID:
        return random_id(exclude=current)
    return map_id if map_id in BY_ID else DEFAULT_ID


def apply(room: "Room", map_id: str) -> GameMap:
    """방에 맵을 실제로 적용한다(발판 교체 + active_map_id 기록)."""
    game_map = get(map_id)
    room.active_map_id = game_map.id
    room.platforms = [dict(p) for p in game_map.platforms]
    return game_map


def spawn_points(room: "Room | None" = None) -> list[tuple[float, float]]:
    """맵의 스폰 지점 목록(없으면 클래식 기준)."""
    map_id = getattr(room, "active_map_id", None) if room is not None else None
    return [(float(x), float(y)) for x, y in get(map_id).spawns]


def fallback_spawn() -> tuple[float, float]:
    """스폰 지점을 못 고를 때의 안전값(월드 상단 랜덤)."""
    return 80.0 + random.random() * (C.WIDTH - 160.0), 130.0
