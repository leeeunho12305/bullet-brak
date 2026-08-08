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

from app.game import blocks as B
from app.game import constants as C

if TYPE_CHECKING:  # 순환 import 방지 (런타임에는 필요 없음)
    from app.game.models import Room

Rect = dict[str, Any]

#: 방장이 "무작위"를 골랐을 때 쓰는 특수 id. 실제 맵이 아니다.
RANDOM_ID = "random"


def rect(x: float, y: float, width: float, height: float) -> Rect:
    """일반 블럭. 종류가 있는 블럭은 아래 jump/mover/ice/spike 를 쓴다."""
    return B.make(x, y, width, height, B.SOLID)


def jump(x: float, y: float, width: float, height: float = 16.0, power: float | None = None) -> Rect:
    """점프대. 지나가면 튀어오른다(power 는 위로 향하는 속도).

    실체가 없으므로(blocks.PASSABLE) **딛고 선 바닥의 윗면과 같은 y** 에 깔아야 한다.
    바닥 위에 얹으면 눈에만 두툼할 뿐 걸리지는 않지만, 바닥과 같은 높이여야 걸어 지나가다
    자연스럽게 튀어오른다.
    """
    return B.make(x, y, width, height, B.JUMP, power=power)


def mover(
    x: float,
    y: float,
    width: float,
    height: float = 18.0,
    axis: str = "x",
    span: float = B.DEFAULT_SPAN,
    speed: float = B.DEFAULT_SPEED,
    phase: float = 0.0,
) -> Rect:
    """이동발판. (x, y) 를 중심으로 axis 축을 따라 ±span 만큼 왕복한다."""
    return B.make(x, y, width, height, B.MOVER, axis=axis, span=span, speed=speed, phase=phase)


def ice(x: float, y: float, width: float, height: float = 20.0) -> Rect:
    """빙판. 밟으면 미끄러진다."""
    return B.make(x, y, width, height, B.ICE)


def spike(x: float, y: float, width: float, height: float = 16.0) -> Rect:
    """가시. 닿아 있는 동안 피해를 입고 튕겨난다."""
    return B.make(x, y, width, height, B.HAZARD)


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
            "platforms": [B.snap(p, full=True) for p in self.platforms],
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
        desc="양쪽 탑과 연결 다리. 바닥으로 떨어져도 점프대로 다시 올라간다.",
        theme=Theme("#0d0a1c", "rgba(177, 151, 252, 0.07)", "#241d3d", "rgba(177, 151, 252, 0.5)"),
        platforms=(
            rect(0, 550, 800, 50),
            rect(140, 330, 60, 220),
            rect(600, 330, 60, 220),
            rect(260, 300, 280, 20),
            rect(50, 190, 160, 20),
            rect(590, 190, 160, 20),
            # 복귀용 점프대는 전부 바닥(y=550) 윗면에 박아 넣는다 — 걸어 지나가면 튀어오른다.
            # 탑과 탑 사이: 다리(x 260~540)에 머리를 박지 않도록 다리 양옆 빈 통로에 놓는다.
            jump(210, 550, 50),
            jump(540, 550, 50),
            # 맵 양쪽 끝. 위쪽 발판(x 50~210 / 590~750)이 없는 바깥 통로라 곧장 꼭대기까지 오른다.
            jump(0, 550, 48),
            jump(752, 550, 48),
        ),
        spawns=((70, 120), (680, 120), (390, 200), (390, 60)),
    ),
    GameMap(
        id="chasm",
        name="협곡",
        emoji="🌋",
        desc="한가운데가 뚫려 있다. 가시를 피하고 점프대로 건너라.",
        theme=Theme("#160a0a", "rgba(255, 143, 77, 0.06)", "#33201a", "rgba(255, 143, 77, 0.5)"),
        platforms=(
            rect(0, 520, 300, 80),
            rect(500, 520, 300, 80),
            # 낙사 구간(x 300~500)과 맞닿은 양쪽 벼랑 끝에만 점프대를 박아 넣는다.
            # 뛰어내리려고 달려오면 그대로 튀어올라 중앙 발판/건너편으로 넘어간다.
            jump(230, 520, 70, power=19.0),
            jump(500, 520, 70, power=19.0),
            rect(370, 430, 60, 40),
            rect(60, 360, 180, 20),
            rect(560, 360, 180, 20),
            rect(330, 250, 140, 20),
            spike(0, 504, 90),
            spike(710, 504, 90),
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
        desc="바닥이 없다. 떠다니는 발판과 점프대만 믿어라.",
        theme=Theme("#04101f", "rgba(77, 171, 247, 0.07)", "#12263f", "rgba(77, 171, 247, 0.55)"),
        platforms=(
            rect(280, 420, 240, 24),
            rect(60, 340, 160, 22),
            rect(580, 340, 160, 22),
            rect(150, 200, 140, 20),
            rect(510, 200, 140, 20),
            rect(40, 520, 120, 20),
            rect(640, 520, 120, 20),
            # 허공을 가로지르는 나룻배. 아래쪽 섬 사이를 천천히 오간다.
            mover(400, 530, 110, 18, axis="x", span=130, speed=0.7),
            # 아래쪽 섬에서 중앙 단상으로 복귀하는 점프대(섬 윗면에 박아 넣는다)
            jump(40, 520, 120, power=19.0),
            jump(640, 520, 120, power=19.0),
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
        desc="건물 두 채와 얼어붙은 하늘다리. 다리 위에서는 멈춰 서기 어렵다.",
        theme=Theme("#081413", "rgba(32, 201, 151, 0.06)", "#14302b", "rgba(32, 201, 151, 0.5)"),
        platforms=(
            rect(0, 560, 800, 40),
            rect(60, 380, 200, 180),
            rect(540, 380, 200, 180),
            rect(100, 240, 120, 18),
            rect(580, 240, 120, 18),
            ice(300, 300, 200, 18),
            rect(330, 470, 140, 18),
        ),
        spawns=((150, 300), (650, 300), (400, 210), (400, 380)),
    ),
    GameMap(
        id="factory",
        name="공장",
        emoji="⚙️",
        desc="점프대·이동발판·빙판·가시가 전부 모여 있다. 지형이 먼저 공격한다.",
        theme=Theme("#0f0a04", "rgba(255, 169, 77, 0.07)", "#2b1f12", "rgba(255, 169, 77, 0.5)"),
        platforms=(
            rect(0, 550, 800, 50),
            # 가시(x 340~460) 양옆의 뻥 뚫린 통로에 점프대를 박아 넣는다 — 달려오다 밟으면
            # 가시를 넘어간다. 빙판(x 0~220)·선반(x 590~800) 밑에 두면 천장에 머리만 박는다.
            jump(220, 550, 100),
            spike(340, 534, 120),
            jump(470, 550, 110),
            ice(0, 430, 220, 20),
            mover(400, 400, 120, 18, axis="x", span=150, speed=0.8),
            mover(730, 380, 70, 18, axis="y", span=90, speed=1.1, phase=1.5),
            rect(590, 300, 210, 20),
            rect(120, 250, 180, 20),
        ),
        # 가시(x 340~460) 바로 위에는 아무도 세우지 않는다 — 떨어지자마자 50 을 깎이면
        # 라운드가 시작도 전에 기울어진다. spawn_points 가 한 번 더 검사한다.
        spawns=((60, 300), (700, 200), (500, 190), (200, 120)),
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
    """방에 맵을 실제로 적용한다(발판 교체 + active_map_id 기록).

    방장이 맵 에디터로 배치를 짜 뒀다면(`room.custom_layout`) 맵의 기본 발판 대신 그걸 깐다.
    테마/스폰은 그대로 고른 맵의 것을 쓴다.
    """
    game_map = get(map_id)
    room.active_map_id = game_map.id
    layout = getattr(room, "custom_layout", None) or game_map.platforms
    room.platforms = [dict(p) for p in layout]
    return game_map


#: 스폰 지점을 가시에서 밀어낼 때 한 번에 옮기는 거리와 시도 횟수
_SHIFT_STEP = 55.0
_SHIFT_TRIES = 12


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _landing_kind(platforms: list[Rect], x: float, y: float) -> str | None:
    """(x, y) 에 세운 플레이어가 그대로 떨어졌을 때 처음 닿는 발판의 종류.

    끝까지 아무것도 없으면 None(낙사 구간)이다. 이동발판은 지금 위치로 판단한다 —
    스폰 직후 몇 틱 사이에 크게 움직이지 않는다.
    """
    left, right = x, x + C.PLAYER_SIZE
    feet = y + C.PLAYER_SIZE
    best_top: float | None = None
    kind: str | None = None
    for block in platforms:
        bx = float(block["x"])
        if bx >= right or bx + float(block["width"]) <= left:
            continue
        top = float(block["y"])
        if top < feet - 1.0:  # 이미 발보다 위에 있는 발판은 밟지 않는다
            continue
        if best_top is None or top < best_top:
            best_top, kind = top, str(block.get("type", B.SOLID))
    return kind


def _push_off_hazard(platforms: list[Rect], x: float, y: float) -> tuple[float, float]:
    """스폰 지점이 가시 위면 좌우로 밀어 안전한 자리를 찾는다(못 찾으면 원래 자리)."""
    if _landing_kind(platforms, x, y) != B.HAZARD:
        return x, y
    limit = C.WIDTH - C.PLAYER_SIZE
    for step in range(1, _SHIFT_TRIES + 1):
        for direction in (-1.0, 1.0):
            moved = _clamp(x + direction * step * _SHIFT_STEP, 0.0, limit)
            if _landing_kind(platforms, moved, y) not in (B.HAZARD, None):
                return moved, y
    return x, y


def spawn_points(room: "Room | None" = None) -> list[tuple[float, float]]:
    """맵의 스폰 지점 목록(없으면 클래식 기준).

    방에 실제로 깔린 발판을 알고 있으면 가시 위에 떨어지는 자리는 옆으로 밀어낸다.
    맵 에디터로 가시를 아무 데나 깔아도 스폰 직후 피해를 입지 않는다.
    """
    map_id = getattr(room, "active_map_id", None) if room is not None else None
    points = [(float(x), float(y)) for x, y in get(map_id).spawns]
    platforms = getattr(room, "platforms", None) if room is not None else None
    if not platforms:
        return points
    return [_push_off_hazard(platforms, x, y) for x, y in points]


def fallback_spawn() -> tuple[float, float]:
    """스폰 지점을 못 고를 때의 안전값(월드 상단 랜덤)."""
    return 80.0 + random.random() * (C.WIDTH - 160.0), 130.0
