// 경쟁전 클라이언트 — 티어 표 캐시와 표시용 계산.
//
// `identity.ts` 와 같은 규칙을 따른다: **여기서 던지는 예외는 하나도 없다.** 서버에
// DB 가 없거나(503) 네트워크가 죽어 있으면 조용히 null/빈 값으로 떨어지고, 로비는
// 경쟁전 칸만 감춘 채 평소처럼 동작한다.
import { api } from '@/api/client';
import { loadToken } from '@/api/identity';
import type {
  LeaderboardPage,
  MatchRecord,
  MyRank,
  RankStats,
  TierInfo,
} from '@/types/ranked';

/** 미배치 자리표시자. 서버의 `ranked.UNRANKED` 와 같은 값이다. */
export const UNRANKED: TierInfo = {
  index: 0,
  group: 'unranked',
  group_name: '미배치',
  division: 0,
  name: '미배치',
  color: '#4a5070',
};

/**
 * 티어 표. 서버가 원본이라 여기서는 받아 두기만 한다.
 *
 * 한 번 받으면 바뀌지 않는 값이라(코드 상수다) 세션 내내 캐시한다. 실패해도 재시도를
 * 걸지 않는다 — 뱃지가 회색으로 보일 뿐이고, 다음 새로고침에 다시 받는다.
 */
let tiers: TierInfo[] = [];
let tierPromise: Promise<TierInfo[]> | null = null;

export async function loadTiers(): Promise<TierInfo[]> {
  if (tiers.length > 0) return tiers;
  // 여러 컴포넌트가 동시에 불러도 요청은 하나만 나가게 한다.
  tierPromise ??= api
    .getTiers()
    .then((list) => {
      tiers = list;
      return list;
    })
    .catch(() => {
      tierPromise = null; // 실패는 캐시하지 않는다
      return [] as TierInfo[];
    });
  return tierPromise;
}

/** 티어 인덱스 -> 표시 정보. 아직 표를 못 받았으면 이름만 있는 값을 준다. */
export function tierOf(index: number): TierInfo {
  if (index <= 0) return UNRANKED;
  return tiers[index - 1] ?? { ...UNRANKED, index, name: `티어 ${index}` };
}

/** 배치 중이면 "배치 2/5", 아니면 "골드 2 · 34 RR". */
export function rankLabel(rank: RankStats): string {
  if (!rank.placed) return `배치 ${rank.placements}/${rank.placement_total}`;
  return `${tierOf(rank.tier).name} · ${rank.rr} RR`;
}

/** 승률(%). 한 판도 안 했으면 0. */
export function winRate(rank: Pick<RankStats, 'wins' | 'losses'>): number {
  const total = rank.wins + rank.losses;
  return total === 0 ? 0 : Math.round((rank.wins / total) * 100);
}

/** "3연승" / "2연패" / 빈 문자열. */
export function streakLabel(streak: number): string {
  if (streak >= 2) return `${streak}연승`;
  if (streak <= -2) return `${-streak}연패`;
  return '';
}

// ── 조회 ────────────────────────────────────────────────────────────────

/**
 * 내 랭크. 로그인 계정이 없거나 서버에 DB 가 없으면 null(= 경쟁전을 쓸 수 없는 상태).
 * "아직 배치 중"과는 다르다 — 그건 `MyRank.rank.placed === false` 로 온다.
 */
export async function fetchMyRank(): Promise<MyRank | null> {
  const token = loadToken();
  if (!token) return null;
  try {
    return await api.getMyRank(token);
  } catch {
    return null;
  }
}

export async function fetchLeaderboard(limit = 50): Promise<LeaderboardPage | null> {
  try {
    return await api.getLeaderboard(limit);
  } catch {
    return null;
  }
}

export async function fetchMatches(limit = 20, rankedOnly = false): Promise<MatchRecord[]> {
  const token = loadToken();
  if (!token) return [];
  try {
    return (await api.getMatches(token, limit, rankedOnly)).entries;
  } catch {
    return [];
  }
}
