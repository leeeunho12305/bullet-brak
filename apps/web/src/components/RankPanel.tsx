// 내 경쟁전 카드 — 티어 / RR 게이지 / 시즌 성적.
//
// 로비에는 한 줄짜리 RankChip 만 두고, 이 자세한 카드는 순위표 모달 위에 얹는다.
// 이 카드는 **경쟁전을 쓸 수 있는 서버에서만** 그려진다(store 의 myRank 가 null 이면
// 호출부가 아예 렌더하지 않는다). 그래서 여기서는 "DB 가 없는 경우"를 다루지 않는다.
import { memo } from 'react';
import type { JSX } from 'react';
import RankBadge from '@/components/RankBadge';
import { streakLabel, tierOf, winRate } from '@/api/ranked';
import type { MyRank } from '@/types/ranked';

interface Props {
  rank: MyRank;
}

function RankPanelInner({ rank }: Props): JSX.Element {
  const { rank: stats, position } = rank;
  const placed = stats.placed;

  // 배치 중에는 판수 진행률을, 배치 후에는 RR(0~100)을 같은 게이지로 보여 준다.
  // 레디언트만 RR 상한이 없어서 100 을 넘을 수 있으므로 잘라 준다.
  const progress = placed
    ? Math.min(100, stats.rr)
    : Math.round((stats.placements / stats.placement_total) * 100);
  const color = placed ? tierOf(stats.tier).color : '#4a5070';
  const streak = streakLabel(stats.streak);
  const played = stats.wins + stats.losses;

  return (
    <div className="rank-card">
      <div className="rank-card-head">
        <RankBadge tier={stats.tier} size={64} placement={!placed} />
        <div className="rank-card-title">
          <strong>{placed ? tierOf(stats.tier).name : '배치 중'}</strong>
          {/* 제목이 이미 티어를 말하고 있다. 여기서는 그 안의 위치만 덧붙인다. */}
          <span className="rank-card-sub">
            {placed
              ? `${stats.rr} RR${position !== null ? ` · ${position}위` : ''}`
              : `${stats.placements} / ${stats.placement_total}판`}
          </span>
        </div>
      </div>

      <div
        className="rank-meter"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={placed ? '랭크 레이팅' : '배치 진행도'}
      >
        <span style={{ width: `${progress}%`, background: color }} />
      </div>
      <p className="hint rank-card-hint">
        {placed
          ? '100 RR 을 채우면 승급하고, 0 RR 에서 한 번 더 지면 강등돼요.'
          : `배치 ${stats.placement_total}판을 마치면 티어가 정해져요.`}
      </p>

      <dl className="rank-stats">
        <div>
          <dt>전적</dt>
          <dd>
            {stats.wins}승 {stats.losses}패
          </dd>
        </div>
        <div>
          <dt>승률</dt>
          <dd>{played === 0 ? '—' : `${winRate(stats)}%`}</dd>
        </div>
        <div>
          <dt>연속</dt>
          <dd className={stats.streak > 0 ? 'is-up' : stats.streak < 0 ? 'is-down' : undefined}>
            {streak || '—'}
          </dd>
        </div>
        <div>
          <dt>최고</dt>
          <dd>{stats.peak_tier > 0 ? tierOf(stats.peak_tier).name : '—'}</dd>
        </div>
      </dl>
    </div>
  );
}

export const RankPanel = memo(RankPanelInner);
export default RankPanel;
