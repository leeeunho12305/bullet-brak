"""경쟁전 랭크 계산 — 발로란트식 티어 + RR + 숨은 MMR.

**DB 도 FastAPI 도 import 하지 않는다.** 여기 있는 건 전부 순수 함수라서 세션 없이
그대로 테스트할 수 있다(`tests/test_ranked.py`). DB 반영은 `app.services.matches` 가
이 모듈의 결과를 받아서 한다.

설계는 발로란트의 경쟁전을 1:1 게임에 맞게 옮긴 것이다.

- **티어**: 아이언 ~ 불멸까지 8계급 × 3디비전 + 레디언트 = 25칸. 0은 미배치.
- **RR(랭크 레이팅)**: 디비전 안에서 0~99. 100을 채우면 승급, 0 밑으로 떨어지면 강등.
  레디언트만 상한이 없다(순위가 곧 등급이라 계속 쌓인다).
- **숨은 MMR**: 실제 실력 점수(Elo). 화면에는 절대 안 보인다. RR 을 얼마나 주고 얼마나
  깎을지를 이 값이 정한다 — 티어보다 실력이 높으면 승리 RR 이 커지고 패배 RR 이 작아져서
  제자리를 찾을 때까지 빠르게 올라간다.
- **배치전**: 5판. 그동안은 티어가 없고 MMR 만 움직이며, 끝나면 MMR 이 가리키는 티어에 꽂힌다.
- **강등 보호**: 0 RR 에 도달한 판은 강등되지 않는다. 그 상태에서 또 져야 내려간다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

# --------------------------------------------------------------------------
# 티어 표
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TierGroup:
    """계급 하나(아이언·브론즈…). `divisions` 가 1이면 디비전 표기가 없다."""

    key: str
    name: str
    divisions: int
    color: str


#: 발로란트와 같은 구성. **순서가 곧 서열이라 중간에 끼워 넣으면 기존 기록의 뜻이 바뀐다.**
#: 추가는 끝에만 하고, 순서를 바꿔야 하면 시즌을 새로 여는 쪽이 맞다.
TIER_GROUPS: tuple[TierGroup, ...] = (
    TierGroup("iron", "아이언", 3, "#6f7480"),
    TierGroup("bronze", "브론즈", 3, "#a3703f"),
    TierGroup("silver", "실버", 3, "#c3c9d4"),
    TierGroup("gold", "골드", 3, "#e3b341"),
    TierGroup("platinum", "플래티넘", 3, "#3fb6c8"),
    TierGroup("diamond", "다이아몬드", 3, "#b57cdd"),
    TierGroup("ascendant", "초월자", 3, "#2fbf7d"),
    TierGroup("immortal", "불멸", 3, "#b0304f"),
    TierGroup("radiant", "레디언트", 1, "#fff3a3"),
)


@dataclass(frozen=True, slots=True)
class TierInfo:
    """티어 한 칸. `index` 는 1부터 시작하고 0은 미배치를 뜻한다."""

    index: int
    group: str
    group_name: str
    #: 1~3. 디비전이 없는 계급(레디언트)은 0.
    division: int
    name: str
    color: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "group": self.group,
            "group_name": self.group_name,
            "division": self.division,
            "name": self.name,
            "color": self.color,
        }


def _build_tiers() -> tuple[TierInfo, ...]:
    out: list[TierInfo] = []
    for group in TIER_GROUPS:
        for d in range(1, group.divisions + 1):
            division = d if group.divisions > 1 else 0
            out.append(
                TierInfo(
                    index=len(out) + 1,
                    group=group.key,
                    group_name=group.name,
                    division=division,
                    name=group.name if division == 0 else f"{group.name} {d}",
                    color=group.color,
                )
            )
    return tuple(out)


TIERS: tuple[TierInfo, ...] = _build_tiers()

#: 가장 높은 티어(= 레디언트)의 인덱스. 그 아래는 전부 RR 0~99 안에서 논다.
MAX_TIER = len(TIERS)
RADIANT = MAX_TIER

UNRANKED = TierInfo(
    index=0, group="unranked", group_name="미배치", division=0, name="미배치", color="#4a5070"
)


def tier_info(index: int) -> TierInfo:
    """티어 인덱스 -> 표시 정보. 범위를 벗어나면 미배치로 본다."""
    if 1 <= index <= MAX_TIER:
        return TIERS[index - 1]
    return UNRANKED


def tier_catalog() -> list[dict[str, Any]]:
    """프런트가 뱃지/리더보드에 쓰는 전체 표."""
    return [t.to_dict() for t in TIERS]


# --------------------------------------------------------------------------
# 상수
# --------------------------------------------------------------------------

#: 배치전 판수. 이걸 채워야 티어가 나온다.
PLACEMENT_MATCHES = 5

#: 새 계정의 시작 MMR 과 그 범위.
BASE_MMR = 1000
MIN_MMR = 100
MAX_MMR = 3000

#: MMR -> 기대 티어 환산. BASE_MMR(1000)이 실버 2(8칸째)가 되도록 잡았다.
MMR_AT_TIER_1 = 720
MMR_PER_TIER = 40

#: Elo K 계수. 배치 중에는 크게 흔들려야 5판 만에 제자리를 찾는다.
K_PLACEMENT = 48
K_NORMAL = 24

#: 승/패의 기본 RR. 여기에 압승 보너스와 MMR 보정이 얹힌다.
BASE_WIN_RR = 20
BASE_LOSS_RR = -18

#: 최종 RR 변동의 상·하한. 발로란트도 대략 이 폭이다.
MIN_WIN_RR, MAX_WIN_RR = 10, 50
MIN_LOSS_RR, MAX_LOSS_RR = -50, -10

#: 압승/접전 보정의 최대치(라운드 점수 차에 비례).
DOMINANCE_BONUS = 6
CLOSE_LOSS_RELIEF = 5

#: 티어 한 칸 차이당 붙는 MMR 보정과 그 한계.
MMR_GAP_WEIGHT = 3
WIN_GAP_RANGE = (-8, 14)
LOSS_GAP_RANGE = (-14, 8)

#: 배치 직후 배정되는 RR. 승급/강등 판정에 여유를 두려고 가운데쯤에 놓는다.
PLACEMENT_START_RR = 30

#: 강등됐을 때 떨어지는 자리. 바로 다시 0으로 밀리지 않을 만큼은 준다.
DEMOTION_RR = 80

#: 승급 시 최소한 이만큼은 들고 올라간다(100을 넘긴 양이 이보다 적어도).
PROMOTION_MIN_RR = 10


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


def expected_tier(mmr: int) -> int:
    """숨은 MMR 이 가리키는 티어. 배치 결과와 RR 보정의 기준이다."""
    raw = 1 + (int(mmr) - MMR_AT_TIER_1) // MMR_PER_TIER
    return int(_clamp(raw, 1, MAX_TIER))


def win_probability(mmr: int, opponent_mmr: int) -> float:
    """Elo 기대 승률. 400점 차이가 10:1 이다."""
    return 1.0 / (1.0 + math.pow(10.0, (int(opponent_mmr) - int(mmr)) / 400.0))


# --------------------------------------------------------------------------
# 랭크 상태
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RankState:
    """한 시즌 안에서의 내 랭크. DB 행의 값 사본이라 여기서는 그냥 숫자다."""

    mmr: int = BASE_MMR
    #: 0 = 배치 미완료.
    tier: int = 0
    rr: int = 0
    placements: int = 0
    #: 0 RR 에서 한 번 버틸 수 있는가. 강등되면 다시 채워진다.
    shield: bool = True

    @property
    def placed(self) -> bool:
        return self.placements >= PLACEMENT_MATCHES and self.tier > 0


@dataclass(frozen=True, slots=True)
class RankChange:
    """한 판이 랭크에 남긴 자국. `to_dict()` 가 그대로 클라이언트로 내려간다."""

    before: RankState
    after: RankState
    won: bool
    rr_delta: int
    #: 배치전이 아직 진행 중이라 티어가 없다.
    placement: bool
    #: 이 판으로 배치가 끝나 티어가 처음 정해졌다.
    placed_now: bool
    promoted: bool
    demoted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "won": self.won,
            "rr_delta": self.rr_delta,
            "placement": self.placement,
            "placement_played": self.after.placements,
            "placement_total": PLACEMENT_MATCHES,
            "placed_now": self.placed_now,
            "promoted": self.promoted,
            "demoted": self.demoted,
            "tier_before": self.before.tier,
            "tier_after": self.after.tier,
            "rr_before": self.before.rr,
            "rr_after": self.after.rr,
            "tier": tier_info(self.after.tier).to_dict(),
        }


def rr_delta(state: RankState, *, won: bool, score: int, opponent_score: int) -> int:
    """이 판의 RR 변동. 승패가 큰 줄기고, 점수 차와 MMR 괴리가 폭을 정한다.

    - **압승/접전**: 5:0 으로 이기면 더 받고, 4:5 로 지면 덜 깎인다. 발로란트가 전투
      성적을 보는 자리를 1:1 에서는 라운드 점수 차가 대신한다.
    - **MMR 괴리**: 숨은 실력이 지금 티어보다 위면 이길 때 더 주고 질 때 덜 깎는다.
      낮으면 반대다. 이 항이 "제자리 찾아가기"를 만든다.
    """
    total = max(1, score + opponent_score)
    gap = expected_tier(state.mmr) - max(1, state.tier)

    if won:
        margin = (score - opponent_score) / total
        base = BASE_WIN_RR + round(margin * DOMINANCE_BONUS)
        base += int(_clamp(gap * MMR_GAP_WEIGHT, *WIN_GAP_RANGE))
        return int(_clamp(base, MIN_WIN_RR, MAX_WIN_RR))

    margin = score / total
    base = BASE_LOSS_RR + round(margin * CLOSE_LOSS_RELIEF)
    base += int(_clamp(gap * MMR_GAP_WEIGHT, *LOSS_GAP_RANGE))
    return int(_clamp(base, MIN_LOSS_RR, MAX_LOSS_RR))


def next_mmr(state: RankState, opponent_mmr: int, *, won: bool) -> int:
    """Elo 갱신. 배치 중에는 K 를 키워서 빨리 수렴시킨다."""
    k = K_PLACEMENT if state.placements < PLACEMENT_MATCHES else K_NORMAL
    expected = win_probability(state.mmr, opponent_mmr)
    moved = state.mmr + k * ((1.0 if won else 0.0) - expected)
    return int(_clamp(round(moved), MIN_MMR, MAX_MMR))


def apply_match(
    state: RankState,
    *,
    opponent_mmr: int,
    won: bool,
    score: int = 0,
    opponent_score: int = 0,
) -> RankChange:
    """한 판의 결과를 랭크에 반영한다. 상태를 바꾸지 않고 새 값을 돌려준다."""
    mmr = next_mmr(state, opponent_mmr, won=won)
    placements = min(PLACEMENT_MATCHES, state.placements + 1)

    # ── 배치전 ────────────────────────────────────────────────────────────
    if state.placements < PLACEMENT_MATCHES:
        done = placements >= PLACEMENT_MATCHES
        after = RankState(
            mmr=mmr,
            tier=expected_tier(mmr) if done else 0,
            rr=PLACEMENT_START_RR if done else 0,
            placements=placements,
            shield=True,
        )
        return RankChange(
            before=state,
            after=after,
            won=won,
            rr_delta=0,
            placement=not done,
            placed_now=done,
            promoted=False,
            demoted=False,
        )

    # ── 배치 이후 ─────────────────────────────────────────────────────────
    delta = rr_delta(state, won=won, score=score, opponent_score=opponent_score)
    tier, rr, shield = state.tier, state.rr + delta, state.shield
    promoted = demoted = False

    if tier >= RADIANT:
        # 레디언트는 승급할 곳이 없다. RR 이 그대로 쌓이고 0 밑으로만 안 간다.
        rr = max(0, rr)
    elif rr >= 100:
        tier += 1
        rr = max(PROMOTION_MIN_RR, rr - 100)
        shield = True
        promoted = True
    elif rr < 0:
        if tier <= 1:
            rr = 0  # 아이언 1 아래는 없다
        elif shield:
            # 0 RR 에 닿은 판은 살려 준다. 다음에 또 지면 그때 내려간다.
            rr, shield = 0, False
        else:
            tier -= 1
            rr, shield = DEMOTION_RR, True
            demoted = True
    elif rr > 0:
        shield = True  # 0 에서 벗어났으면 보호막이 다시 찬다

    after = replace(state, mmr=mmr, tier=tier, rr=int(rr), placements=placements, shield=shield)
    return RankChange(
        before=state,
        after=after,
        won=won,
        rr_delta=delta,
        placement=False,
        placed_now=False,
        promoted=promoted,
        demoted=demoted,
    )


def soft_reset(state: RankState) -> RankState:
    """시즌이 바뀔 때의 이월. 발로란트처럼 실력은 일부만 기억하고 배치를 다시 본다.

    MMR 을 평균 쪽으로 20% 당겨 두면, 잘하던 사람은 배치 몇 판으로 제자리를 찾고
    새 시즌의 상위 티어가 첫날부터 굳어 버리지는 않는다.
    """
    pulled = round(state.mmr * 0.8 + BASE_MMR * 0.2)
    return RankState(mmr=int(_clamp(pulled, MIN_MMR, MAX_MMR)), tier=0, rr=0, placements=0)
