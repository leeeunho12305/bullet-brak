"""발판(블럭) 종류와 그 효과.

지금까지 발판은 전부 "그냥 막힌 네모"였다. 여기서 종류를 붙여 점프대·이동발판·빙판·
가시를 만든다. 발판은 여전히 `dict` 하나로 표현된다(방마다 사본을 갖고, 스냅샷으로
그대로 나간다) — 종류별 추가 필드는 아래 표가 단일 출처다.

  solid   일반 블럭 (기본값)
  jump    점프대   : 위에서 밟으면 `power` 만큼 튀어오른다
  mover   이동발판 : `axis` 축으로 `span` 만큼 사인 왕복한다. 올라탄 사람을 같이 나른다
  ice     빙판     : 마찰이 거의 없다(미끄러진다)
  hazard  가시     : 닿으면 아프다. 밟으면 위로 튕겨낸다

constants 외에는 아무것도 import 하지 않는다(순수 데이터/수학 — maps 가 이 모듈을 쓴다).
"""

from __future__ import annotations

import math
from typing import Any

from app.game import constants as C

Rect = dict[str, Any]

SOLID = "solid"
JUMP = "jump"
MOVER = "mover"
ICE = "ice"
HAZARD = "hazard"

#: 맵 에디터가 고를 수 있는 종류(순서가 팔레트 순서다)
TYPES: tuple[str, ...] = (SOLID, JUMP, MOVER, ICE, HAZARD)

#: 점프대 기본 위력(음수 = 위). -21 이면 약 367px 상승 — 탑 꼭대기까지 닿는다.
DEFAULT_JUMP_POWER = 21.0
MAX_JUMP_POWER = 34.0

#: 이동발판 기본값
DEFAULT_SPAN = 120.0
MAX_SPAN = 400.0
DEFAULT_SPEED = 0.9  # 초당 왕복 위상(라디안). 1.0 이면 한 바퀴에 약 7초.
MAX_SPEED = 3.0

#: 빙판 마찰(일반 FRICTION=0.8 대비 훨씬 잘 미끄러진다)
ICE_FRICTION = 0.985
#: 가시에 닿아 있는 동안의 초당 피해와 튕겨내는 속도
HAZARD_DPS = 26.0
HAZARD_BOUNCE = 9.0

#: 에디터가 만들 수 있는 블럭 크기/개수 한계(악의적 페이로드 차단)
MIN_SIZE = 10.0
MAX_BLOCKS = 40


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return fallback
    return f if math.isfinite(f) else fallback


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------
# 생성
# --------------------------------------------------------------------------


def make(x: float, y: float, width: float, height: float, kind: str = SOLID, **opts: Any) -> Rect:
    """블럭 하나. 종류별 필드는 기본값으로 채운다(맵 카탈로그와 에디터의 공용 생성자)."""
    block: Rect = {
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
        "type": kind if kind in TYPES else SOLID,
    }
    if block["type"] == JUMP:
        block["power"] = _clamp(
            _num(opts.get("power"), DEFAULT_JUMP_POWER), 6.0, MAX_JUMP_POWER
        )
    elif block["type"] == MOVER:
        block["axis"] = "y" if str(opts.get("axis", "x")) == "y" else "x"
        block["span"] = _clamp(_num(opts.get("span"), DEFAULT_SPAN), 20.0, MAX_SPAN)
        block["speed"] = _clamp(_num(opts.get("speed"), DEFAULT_SPEED), 0.1, MAX_SPEED)
        block["phase"] = _num(opts.get("phase"), 0.0) % (math.pi * 2)
        # 왕복의 중심. x/y 는 여기서 매 틱 다시 계산되므로 원점을 따로 기억한다.
        block["ox"] = block["x"]
        block["oy"] = block["y"]
    return block


def normalize(raw: Any) -> Rect | None:
    """클라이언트(맵 에디터)가 보낸 블럭 하나를 검증한다. 못 쓰면 None."""
    if not isinstance(raw, dict):
        return None
    width = _clamp(_num(raw.get("width")), MIN_SIZE, C.WIDTH)
    height = _clamp(_num(raw.get("height")), MIN_SIZE, C.HEIGHT)
    x = _clamp(_num(raw.get("x")), 0.0, C.WIDTH - width)
    y = _clamp(_num(raw.get("y")), 0.0, C.HEIGHT - height)
    kind = raw.get("type")
    return make(
        x,
        y,
        width,
        height,
        kind if isinstance(kind, str) else SOLID,
        power=raw.get("power"),
        axis=raw.get("axis"),
        span=raw.get("span"),
        speed=raw.get("speed"),
        phase=raw.get("phase"),
    )


def normalize_all(raw: Any) -> list[Rect]:
    """블럭 목록 검증. 못 쓰는 항목은 버리고, 개수 상한을 넘으면 잘라낸다."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[Rect] = []
    for item in raw:
        block = normalize(item)
        if block is not None:
            out.append(block)
        if len(out) >= MAX_BLOCKS:
            break
    return out


def snap(block: Rect, full: bool = False) -> Rect:
    """클라이언트용 사본. 서버 내부 계산용 필드(ox/oy/dx/dy)는 빼고 보낸다.

    `full=True` 는 대기실(room_state / 맵 카탈로그)용이다 — 맵 에디터가 이동발판을 다시
    열었을 때 왕복 폭·속도를 그대로 이어받아야 하므로 그 값까지 싣는다. 60Hz 스냅샷에서는
    쓰이지 않는 값이라 기본값에서는 뺀다.
    """
    out: Rect = {
        "x": block["x"],
        "y": block["y"],
        "width": block["width"],
        "height": block["height"],
    }
    kind = str(block.get("type", SOLID))
    if kind != SOLID:
        out["type"] = kind
    if kind == JUMP:
        out["power"] = block.get("power", DEFAULT_JUMP_POWER)
    elif kind == MOVER:
        out["axis"] = block.get("axis", "x")
        if full:
            # 왕복의 중심(ox/oy)을 좌표로 준다. 지금 위치를 주면 다시 저장할 때마다
            # 발판이 흘러가 버린다.
            out["x"] = block.get("ox", block["x"])
            out["y"] = block.get("oy", block["y"])
            out["span"] = block.get("span", DEFAULT_SPAN)
            out["speed"] = block.get("speed", DEFAULT_SPEED)
    return out


# --------------------------------------------------------------------------
# 이동발판
# --------------------------------------------------------------------------


def update_movers(room: Any) -> None:
    """이동발판을 이번 틱 위치로 옮기고, 옮긴 양을 dx/dy 에 남긴다.

    엔티티 물리보다 **먼저** 돌아야 한다. 올라탄 사람은 sim 이 dx/dy 만큼 같이 옮긴다.
    """
    for block in room.platforms:
        if block.get("type") != MOVER:
            continue
        t = room.tick * C.TICK_SECONDS
        offset = math.sin(t * float(block["speed"]) + float(block["phase"])) * float(block["span"])
        if block["axis"] == "y":
            new_x, new_y = float(block["ox"]), float(block["oy"]) + offset
        else:
            new_x, new_y = float(block["ox"]) + offset, float(block["oy"])
        block["dx"] = new_x - float(block["x"])
        block["dy"] = new_y - float(block["y"])
        block["x"] = new_x
        block["y"] = new_y


def carry(entity: Any, room: Any) -> None:
    """직전 틱에 올라타 있던 이동발판을 따라 엔티티를 옮긴다.

    엔티티가 자기 속도를 적용하기 전에 호출한다. 태워 준 발판이 사라졌거나(맵 교체)
    더 이상 이동발판이 아니면 조용히 무시한다.
    """
    index = getattr(entity, "ride", -1)
    if index < 0 or index >= len(room.platforms):
        entity.ride = -1
        return
    block = room.platforms[index]
    if block.get("type") == MOVER:
        entity.x += float(block.get("dx", 0.0))
        entity.y += float(block.get("dy", 0.0))
    entity.ride = -1


# --------------------------------------------------------------------------
# 밟았을 때의 효과
# --------------------------------------------------------------------------


def on_contact(entity: Any, block: Rect, side: str | None, index: int) -> float:
    """충돌 직후의 블럭 효과. 입은 피해를 돌려준다(가시만 0 이 아니다).

    `side` 는 physics.resolve_platform_collision 의 반환값("top" 이면 위에서 밟았다).
    """
    if side is None:
        return 0.0
    kind = block.get("type", SOLID)

    if kind == HAZARD:
        # 어느 면에 닿았든 아프다. 밟은 쪽으로 튕겨내서 계속 갈리지 않게 한다.
        if side == "top":
            entity.vy = -HAZARD_BOUNCE
            entity.grounded = False
        elif side == "bottom":
            entity.vy = HAZARD_BOUNCE * 0.5
        elif side in ("left", "right"):
            # "left" 는 왼쪽 면 안으로 파고들어 왼쪽으로 밀려난 것 — 그 방향으로 더 밀어낸다.
            entity.vx = HAZARD_BOUNCE * (1.0 if side == "left" else -1.0)
        return HAZARD_DPS * C.TICK_SECONDS

    if side != "top":
        return 0.0

    if kind == JUMP:
        entity.vy = -float(block.get("power", DEFAULT_JUMP_POWER))
        entity.grounded = False
        # 점프대로 뜬 뒤에도 공중 점프를 온전히 쓸 수 있다(밟자마자 0 으로 리셋된다).
        if hasattr(entity, "jumps"):
            entity.jumps = 0
    elif kind == MOVER:
        entity.ride = index
    elif kind == ICE:
        entity.on_ice = True
    return 0.0
