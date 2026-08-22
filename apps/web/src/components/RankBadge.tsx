// 티어 뱃지 — 발로란트풍 육각 엠블럼 + 디비전 셰브런.
//
// 색과 이름은 서버가 준 티어 표에서만 온다(`@/api/ranked`). 여기서 하는 일은 그
// 색으로 도형을 칠하는 것뿐이라, 계급을 추가해도 이 파일은 손댈 필요가 없다.
import { memo } from 'react';
import type { JSX } from 'react';
import { tierOf } from '@/api/ranked';

interface Props {
  /** 티어 인덱스(1~25). 0 이면 미배치 뱃지가 그려진다. */
  tier: number;
  /** 한 변 크기(px). 목록에서는 28, 로비 카드에서는 72쯤 쓴다. */
  size?: number;
  /** 티어 이름을 옆에 같이 쓸지. */
  label?: boolean;
  /** 배치 중이라 티어가 없는 상태. 이름 대신 "배치 중"을 보여 준다. */
  placement?: boolean;
}

/** 육각 엠블럼의 외곽선. viewBox 48×54 기준. */
const HEX = 'M24 1 L45 13 L45 37 L24 53 L3 37 L3 13 Z';

function RankBadgeInner({ tier, size = 40, label = false, placement = false }: Props): JSX.Element {
  const info = tierOf(tier);
  const unranked = placement || info.index <= 0;
  const color = unranked ? '#4a5070' : info.color;
  // 레디언트는 디비전이 없다 — 셰브런 대신 중앙에 별을 하나 놓는다.
  const chevrons = info.division;

  return (
    <span
      className="rank-badge"
      style={{ ['--rank-color' as string]: color }}
      // 목록에 들어가는 작은 뱃지는 모양만으로 못 읽는다. 올리면 이름이 뜨게 한다.
      title={unranked ? '미배치' : info.name}
    >
      <svg
        width={size}
        height={size * 1.125}
        viewBox="0 0 48 54"
        role="img"
        aria-label={unranked ? '미배치' : info.name}
      >
        <defs>
          {/* id 를 티어별로 나눠야 한 화면에 여러 뱃지가 있을 때 섞이지 않는다. */}
          <linearGradient id={`rank-g-${info.index}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.95" />
            <stop offset="100%" stopColor={color} stopOpacity="0.25" />
          </linearGradient>
        </defs>

        <path d={HEX} fill={`url(#rank-g-${info.index})`} stroke={color} strokeWidth="2" />
        <path d={HEX} fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="1" transform="scale(0.82) translate(5.3 6)" />

        {unranked ? (
          <text
            x="24"
            y="31"
            textAnchor="middle"
            fontSize="15"
            fontWeight="700"
            fill="rgba(255,255,255,0.7)"
          >
            ?
          </text>
        ) : chevrons === 0 ? (
          // 레디언트
          <path
            d="M24 13 L28 23 L38 27 L28 31 L24 41 L20 31 L10 27 L20 23 Z"
            fill="#fffdf0"
            stroke={color}
            strokeWidth="1"
          />
        ) : (
          Array.from({ length: chevrons }, (_, i) => (
            <path
              key={i}
              d={`M14 ${21 + i * 8} L24 ${14 + i * 8} L34 ${21 + i * 8}`}
              fill="none"
              stroke="#fff"
              strokeOpacity={0.55 + i * 0.2}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))
        )}
      </svg>
      {label ? (
        <span className="rank-badge-name">{unranked ? '배치 중' : info.name}</span>
      ) : null}
    </span>
  );
}

export const RankBadge = memo(RankBadgeInner);
export default RankBadge;
