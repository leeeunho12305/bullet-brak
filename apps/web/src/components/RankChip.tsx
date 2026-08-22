// 로비의 랭크 한 줄 — 뱃지 + 티어 + RR + 순위.
//
// 로비는 이미 빽빽한 화면이라 여기서는 **한 줄만** 쓴다. 승률·연승·최고 티어 같은
// 자세한 값은 이 칩을 눌러서 여는 모달(RankPanel)로 넘겼다.
import { memo } from 'react';
import type { JSX } from 'react';
import RankBadge from '@/components/RankBadge';
import { tierOf } from '@/api/ranked';
import type { MyRank } from '@/types/ranked';

interface Props {
  rank: MyRank;
  /** 순위표 / 전적 모달 열기. */
  onClick(): void;
}

function RankChipInner({ rank, onClick }: Props): JSX.Element {
  const { rank: stats, position } = rank;
  const placed = stats.placed;
  const color = placed ? tierOf(stats.tier).color : '#4a5070';

  const detail = placed
    ? `${stats.rr} RR${position !== null ? ` · ${position}위` : ''}`
    : `배치 ${stats.placements}/${stats.placement_total}`;

  return (
    <button
      type="button"
      className="rank-chip"
      style={{ ['--rank-color' as string]: color }}
      onClick={onClick}
      aria-label={`경쟁전 ${placed ? tierOf(stats.tier).name : '배치 중'} — 순위표와 전적 보기`}
    >
      <RankBadge tier={stats.tier} size={30} placement={!placed} />
      <span className="rank-chip-text">
        <strong>{placed ? tierOf(stats.tier).name : '배치 중'}</strong>
        <span className="muted">{detail}</span>
      </span>
      <span className="rank-chip-go" aria-hidden>
        🏆
      </span>
    </button>
  );
}

export const RankChip = memo(RankChipInner);
export default RankChip;
