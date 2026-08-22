// 경쟁전 타입 — docs/PROTOCOL.md §1.2 와 1:1 대응.
//
// **티어 표를 여기 적어 두지 않는다.** 이름과 색은 서버(`GET /api/ranked/tiers`)가
// 유일한 원본이고, 프런트는 부팅할 때 한 번 받아서 캐시한다(`@/api/ranked`).
// 같은 표를 양쪽에 적어 두면 계급을 하나 손대는 순간 반드시 어긋난다.

/** 티어 한 칸. index 는 1(아이언 1) ~ 25(레디언트), 0 은 미배치. */
export interface TierInfo {
  index: number;
  /** 'iron' | 'bronze' | … | 'radiant'. 뱃지 모양을 이 값으로 가른다. */
  group: string;
  group_name: string;
  /** 1~3. 디비전이 없는 계급(레디언트)은 0. */
  division: number;
  name: string;
  color: string;
}

export interface Season {
  id: number;
  key: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  is_active: boolean;
}

/** 한 시즌의 내 랭크. placed 가 false 면 tier/rr 은 아직 의미가 없다. */
export interface RankStats {
  tier: number;
  rr: number;
  placements: number;
  placement_total: number;
  placed: boolean;
  peak_tier: number;
  peak_rr: number;
  wins: number;
  losses: number;
  /** 양수면 연승, 음수면 연패. */
  streak: number;
  best_streak: number;
  rounds_won: number;
  rounds_lost: number;
}

export interface MyRank {
  season: Season;
  rank: RankStats;
  /** 리더보드 순위. 배치 중이면 null. */
  position: number | null;
}

export interface LeaderboardEntry {
  position: number;
  account_id: string;
  nickname: string;
  customization: Record<string, unknown>;
  rank: RankStats;
}

export interface LeaderboardPage {
  season: Season;
  entries: LeaderboardEntry[];
}

/** 전적 한 줄. 일반전이면 rr_delta 는 0 이다. */
export interface MatchRecord {
  id: string;
  ranked: boolean;
  mode: string;
  map_id: string;
  rounds: number;
  duration_sec: number;
  /** 상대가 도중에 나가서 끝난 판. */
  forfeit: boolean;
  ended_at: string;
  won: boolean;
  score: number;
  opponent_score: number;
  opponent_nickname: string;
  rr_delta: number;
  placement: boolean;
  tier_before: number;
  tier_after: number;
  rr_after: number;
}

/**
 * 매치가 끝난 뒤 서버가 밀어 주는 랭크 변동(WS `rank_update`).
 *
 * DB 쓰기가 끝난 다음에 오므로 `match_over` 이벤트보다 **한 박자 늦다** —
 * 종료 오버레이는 이 값이 아직 없을 때도 그려질 수 있어야 한다.
 */
export interface RankChange {
  won: boolean;
  rr_delta: number;
  /** 배치전이 아직 진행 중이라 티어가 없다. */
  placement: boolean;
  placement_played: number;
  placement_total: number;
  /** 이 판으로 배치가 끝나 티어가 처음 정해졌다. */
  placed_now: boolean;
  promoted: boolean;
  demoted: boolean;
  tier_before: number;
  tier_after: number;
  rr_before: number;
  rr_after: number;
  /** 변동 후 티어의 표시 정보(서버가 같이 실어 준다). */
  tier: TierInfo;
}
