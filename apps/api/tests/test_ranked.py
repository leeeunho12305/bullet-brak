"""경쟁전 랭크 계산 — 순수 함수만 본다(DB 없음).

여기서 지키려는 것은 "발로란트처럼 굴러가는가"다.

- 배치 5판을 채워야 티어가 나온다
- 100 RR 을 채우면 승급, 0 밑으로 떨어지면(한 번 버틴 뒤에) 강등
- 숨은 MMR 이 표시 티어보다 높으면 승리 RR 이 커진다
- 아이언 1 아래와 레디언트 위로는 나가지 않는다
"""

from __future__ import annotations

from app.services import ranked


# --------------------------------------------------------------------------
# 티어 표
# --------------------------------------------------------------------------


def test_tier_table_is_valorant_shaped() -> None:
    """8계급 × 3디비전 + 레디언트 = 25칸."""
    assert ranked.MAX_TIER == 25
    assert ranked.tier_info(1).name == "아이언 1"
    assert ranked.tier_info(10).name == "골드 1"
    assert ranked.tier_info(24).name == "불멸 3"
    assert ranked.tier_info(25).name == "레디언트"
    assert ranked.tier_info(25).division == 0  # 레디언트는 디비전이 없다


def test_out_of_range_tier_is_unranked() -> None:
    assert ranked.tier_info(0).group == "unranked"
    assert ranked.tier_info(999).group == "unranked"


def test_tier_catalog_is_ordered_and_complete() -> None:
    catalog = ranked.tier_catalog()
    assert len(catalog) == ranked.MAX_TIER
    assert [t["index"] for t in catalog] == list(range(1, ranked.MAX_TIER + 1))


# --------------------------------------------------------------------------
# MMR
# --------------------------------------------------------------------------


def test_base_mmr_lands_in_silver() -> None:
    """새 계정의 기본 MMR 은 표의 한가운데쯤(실버)이어야 한다."""
    assert ranked.tier_info(ranked.expected_tier(ranked.BASE_MMR)).group == "silver"


def test_expected_tier_is_clamped_at_both_ends() -> None:
    assert ranked.expected_tier(-9999) == 1
    assert ranked.expected_tier(9999) == ranked.MAX_TIER


def test_win_probability_is_symmetric() -> None:
    assert ranked.win_probability(1000, 1000) == 0.5
    assert ranked.win_probability(1400, 1000) > 0.9
    assert ranked.win_probability(1000, 1400) < 0.1


def test_beating_a_stronger_opponent_moves_mmr_more() -> None:
    placed = ranked.RankState(mmr=1000, tier=8, rr=50, placements=ranked.PLACEMENT_MATCHES)
    vs_equal = ranked.next_mmr(placed, 1000, won=True) - placed.mmr
    vs_stronger = ranked.next_mmr(placed, 1400, won=True) - placed.mmr
    assert vs_stronger > vs_equal > 0


# --------------------------------------------------------------------------
# 배치전
# --------------------------------------------------------------------------


def test_placement_gives_no_tier_until_finished() -> None:
    state = ranked.RankState()
    for played in range(1, ranked.PLACEMENT_MATCHES):
        change = ranked.apply_match(state, opponent_mmr=1000, won=True)
        assert change.placement is True
        assert change.after.tier == 0
        assert change.rr_delta == 0
        assert change.after.placements == played
        state = change.after

    final = ranked.apply_match(state, opponent_mmr=1000, won=True)
    assert final.placed_now is True
    assert final.placement is False
    assert final.after.tier > 0
    assert final.after.rr == ranked.PLACEMENT_START_RR
    assert final.after.placed is True


def test_winning_every_placement_lands_higher_than_losing_every_one() -> None:
    def run(won: bool) -> int:
        state = ranked.RankState()
        for _ in range(ranked.PLACEMENT_MATCHES):
            state = ranked.apply_match(state, opponent_mmr=1000, won=won).after
        return state.tier

    assert run(True) > run(False)


# --------------------------------------------------------------------------
# RR
# --------------------------------------------------------------------------


def _placed(tier: int, rr: int, mmr: int | None = None) -> ranked.RankState:
    """배치를 마친 상태 하나. mmr 을 생략하면 그 티어에 딱 맞는 값으로 둔다."""
    if mmr is None:
        mmr = ranked.MMR_AT_TIER_1 + (tier - 1) * ranked.MMR_PER_TIER
    return ranked.RankState(mmr=mmr, tier=tier, rr=rr, placements=ranked.PLACEMENT_MATCHES)


def test_win_gains_and_loss_drops_within_bounds() -> None:
    state = _placed(10, 50)
    win = ranked.rr_delta(state, won=True, score=5, opponent_score=3)
    loss = ranked.rr_delta(state, won=False, score=3, opponent_score=5)
    assert ranked.MIN_WIN_RR <= win <= ranked.MAX_WIN_RR
    assert ranked.MIN_LOSS_RR <= loss <= ranked.MAX_LOSS_RR


def test_dominant_win_beats_a_close_one() -> None:
    state = _placed(10, 50)
    sweep = ranked.rr_delta(state, won=True, score=5, opponent_score=0)
    close = ranked.rr_delta(state, won=True, score=5, opponent_score=4)
    assert sweep > close


def test_close_loss_hurts_less_than_a_sweep() -> None:
    state = _placed(10, 50)
    close = ranked.rr_delta(state, won=False, score=4, opponent_score=5)
    swept = ranked.rr_delta(state, won=False, score=0, opponent_score=5)
    assert close > swept  # 둘 다 음수 — 접전 쪽이 덜 깎인다


def test_underranked_player_climbs_faster() -> None:
    """숨은 실력이 표시 티어보다 훨씬 위면 이길 때 더 받고 질 때 덜 깎인다."""
    fair = _placed(10, 50)
    smurf = _placed(10, 50, mmr=ranked.MMR_AT_TIER_1 + 20 * ranked.MMR_PER_TIER)

    assert ranked.rr_delta(smurf, won=True, score=5, opponent_score=3) > ranked.rr_delta(
        fair, won=True, score=5, opponent_score=3
    )
    assert ranked.rr_delta(smurf, won=False, score=3, opponent_score=5) > ranked.rr_delta(
        fair, won=False, score=3, opponent_score=5
    )


# --------------------------------------------------------------------------
# 승급 / 강등
# --------------------------------------------------------------------------


def test_reaching_100_rr_promotes_and_carries_the_overflow() -> None:
    change = ranked.apply_match(_placed(10, 95), opponent_mmr=1000, won=True, score=5)
    assert change.promoted is True
    assert change.after.tier == 11
    assert change.after.rr >= ranked.PROMOTION_MIN_RR
    assert change.after.rr < 100


def test_zero_rr_survives_one_loss_then_demotes() -> None:
    """0 RR 에 닿은 판은 살려 준다. 그 다음 패배에서 내려간다."""
    first = ranked.apply_match(_placed(10, 5), opponent_mmr=1000, won=False, opponent_score=5)
    assert first.demoted is False
    assert first.after.rr == 0
    assert first.after.shield is False

    second = ranked.apply_match(first.after, opponent_mmr=1000, won=False, opponent_score=5)
    assert second.demoted is True
    assert second.after.tier == 9
    assert second.after.rr == ranked.DEMOTION_RR
    assert second.after.shield is True  # 강등되면 보호막이 다시 찬다


def test_shield_refills_after_climbing_off_zero() -> None:
    at_zero = ranked.RankState(
        mmr=1000, tier=10, rr=0, placements=ranked.PLACEMENT_MATCHES, shield=False
    )
    recovered = ranked.apply_match(at_zero, opponent_mmr=1000, won=True, score=5)
    assert recovered.after.rr > 0
    assert recovered.after.shield is True


def test_iron_one_never_falls_below_zero() -> None:
    state = _placed(1, 0)
    for _ in range(5):
        state = ranked.apply_match(state, opponent_mmr=1000, won=False, opponent_score=5).after
    assert state.tier == 1
    assert state.rr == 0


def test_radiant_accumulates_rr_instead_of_promoting() -> None:
    """레디언트 위로는 갈 곳이 없다. RR 이 100 을 넘어도 그대로 쌓인다."""
    state = _placed(ranked.RADIANT, 95, mmr=ranked.MAX_MMR)
    change = ranked.apply_match(state, opponent_mmr=1000, won=True, score=5)
    assert change.promoted is False
    assert change.after.tier == ranked.RADIANT
    assert change.after.rr > 100


# --------------------------------------------------------------------------
# 시즌 이월
# --------------------------------------------------------------------------


def test_soft_reset_clears_tier_but_remembers_skill() -> None:
    veteran = _placed(22, 60, mmr=1800)
    fresh = ranked.soft_reset(veteran)
    assert fresh.tier == 0
    assert fresh.rr == 0
    assert fresh.placements == 0
    # 평균 쪽으로 당겨지되, 완전히 초기화되지는 않는다.
    assert ranked.BASE_MMR < fresh.mmr < veteran.mmr


def test_change_serializes_for_the_client() -> None:
    change = ranked.apply_match(_placed(10, 50), opponent_mmr=1000, won=True, score=5)
    payload = change.to_dict()
    assert payload["won"] is True
    assert payload["rr_delta"] > 0
    assert payload["tier"]["name"] == ranked.tier_info(change.after.tier).name
    # 숨은 점수는 어떤 형태로도 새 나가면 안 된다.
    assert "mmr" not in payload
