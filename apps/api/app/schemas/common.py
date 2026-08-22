"""여러 스키마가 함께 쓰는 조각 — 아바타 커스터마이즈.

`messages.py` / `accounts.py` 둘 다 필요해서 따로 뒀다(파일당 400줄).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.game import constants as C


class PartOffset(BaseModel):
    """파츠를 몸통 박스 대비 비율만큼 밀어 놓은 값(편집기의 드래그 결과)."""

    model_config = ConfigDict(extra="ignore")

    x: float = 0.0
    y: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def _clamp_axis(cls, v: float) -> float:
        f = float(v)
        if not math.isfinite(f):
            return 0.0
        return max(-C.MAX_PART_OFFSET, min(C.MAX_PART_OFFSET, f))


class Customization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eye: int = 0
    mouth: int = 0
    detail: int = 0
    detail2: int = 0
    color: str = "#ff6b6b"
    offsets: dict[str, PartOffset] = Field(default_factory=dict)

    @field_validator("eye", "mouth", "detail", "detail2")
    @classmethod
    def _clamp_index(cls, v: int) -> int:
        return max(0, min(C.MAX_PART_INDEX, int(v)))

    @field_validator("offsets")
    @classmethod
    def _known_slots(cls, v: dict[str, PartOffset]) -> dict[str, PartOffset]:
        return {k: off for k, off in v.items() if k in C.PART_SLOTS}

    @field_validator("color")
    @classmethod
    def _safe_color(cls, v: str) -> str:
        v = (v or "").strip()
        return v if v.startswith("#") and 4 <= len(v) <= 9 else "#ff6b6b"
