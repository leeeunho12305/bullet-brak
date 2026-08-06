// 라운드 승수를 나타내는 원. 1승이면 왼쪽 반쪽, 2승(=1점)이면 꽉 찬다.
// 채우는 색은 항상 그 플레이어(팀)의 색을 그대로 쓴다.
import type { CSSProperties, JSX } from 'react';
import { ROUNDS_TO_SCORE } from '@/types/game';

/** viewBox 100 기준. 위 꼭짓점에서 왼쪽으로 돌아 아래 꼭짓점까지 = 왼쪽 반원 */
const LEFT_HALF = 'M50 6 A44 44 0 0 0 50 94 Z';

interface ScoreOrbProps {
  /** 이번 1점까지 딴 라운드 수(0 ~ ROUNDS_TO_SCORE) */
  wins: number;
  /** 플레이어 색(HUD 스와치와 같은 값) */
  color: string;
  /** 지름(px) */
  size?: number;
}

export function ScoreOrb({ wins, color, size = 18 }: ScoreOrbProps): JSX.Element {
  const won = Math.max(0, Math.min(ROUNDS_TO_SCORE, Math.floor(wins)));
  // 글로우를 CSS 쪽에서 같은 색으로 깔기 위해 변수로 넘긴다.
  const style = { '--orb': color, width: size, height: size } as CSSProperties;

  return (
    <svg className={`score-orb${won > 0 ? ' lit' : ''}`} style={style} viewBox="0 0 100 100">
      <title>{`${won}/${ROUNDS_TO_SCORE} rounds won`}</title>
      {won >= ROUNDS_TO_SCORE && <circle cx="50" cy="50" r="44" fill={color} />}
      {won > 0 && won < ROUNDS_TO_SCORE && <path d={LEFT_HALF} fill={color} />}
      <circle cx="50" cy="50" r="44" fill="none" stroke={color} strokeWidth="7" />
      <line x1="50" y1="6" x2="50" y2="94" stroke={color} strokeWidth="7" />
    </svg>
  );
}

export default ScoreOrb;
