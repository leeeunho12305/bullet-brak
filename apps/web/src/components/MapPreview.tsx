// 맵 미리보기 — 서버가 준 발판/스폰 좌표를 800x600 viewBox 에 그대로 그린다.
// 인게임 캔버스와 같은 좌표계라 실제 지형과 1:1 로 대응한다.
import { memo } from 'react';
import type { JSX } from 'react';
import { WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { MapInfo } from '@/types/game';

interface Props {
  map: MapInfo;
  /** 스폰 지점 표시 여부(작은 썸네일에서는 끈다) */
  showSpawns?: boolean;
  className?: string;
}

function MapPreviewInner({ map, showSpawns = true, className }: Props): JSX.Element {
  const { theme, platforms, spawns } = map;
  return (
    <svg
      className={className ? `map-preview ${className}` : 'map-preview'}
      viewBox={`0 0 ${WORLD_WIDTH} ${WORLD_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`${map.name} 맵 미리보기`}
    >
      <rect x={0} y={0} width={WORLD_WIDTH} height={WORLD_HEIGHT} fill={theme.bg} />
      {platforms.map((p, i) => (
        <rect
          key={`p${i}`}
          x={p.x}
          y={p.y}
          width={p.width}
          height={p.height}
          fill={theme.platform}
          stroke={theme.edge}
          strokeWidth={4}
        />
      ))}
      {showSpawns
        ? spawns.map((s, i) => (
            <circle key={`s${i}`} cx={s.x + 15} cy={s.y + 15} r={13} fill={theme.edge} opacity={0.55} />
          ))
        : null}
    </svg>
  );
}

export const MapPreview = memo(MapPreviewInner);
export default MapPreview;
