// 조작키 안내. 예전에는 인게임 캔버스 위에 겹쳐 놨는데 시야를 가려서
// 로비("게임 꾸미기" 아래)로 옮겼다. 튜토리얼에서도 같은 표를 쓴다.
import type { JSX } from 'react';

export interface KeyEntry {
  keys: string[];
  label: string;
  highlight?: boolean;
}

export const CONTROL_ENTRIES: KeyEntry[] = [
  { keys: ['A', 'D'], label: '이동' },
  { keys: ['W', 'Space'], label: '점프' },
  { keys: ['마우스'], label: '조준' },
  { keys: ['좌클릭'], label: '사격' },
  { keys: ['좌클릭 길게', 'E'], label: '강공격' },
  { keys: ['우클릭', 'Shift'], label: '가드' },
  { keys: ['Enter'], label: '채팅' },
  { keys: ['Tab'], label: '정보 보기(대미지·스탯·카드)', highlight: true },
];

interface Props {
  /** 제목 줄을 붙일지(튜토리얼 안에서는 끈다) */
  title?: string;
}

export default function ControlsGuide({ title = '조작법' }: Props): JSX.Element {
  return (
    <div className="controls-guide">
      {title ? <h3 className="section-title">{title}</h3> : null}
      <ul className="controls-list">
        {CONTROL_ENTRIES.map((entry) => (
          <li key={entry.label} className={entry.highlight ? 'controls-row is-hl' : 'controls-row'}>
            <span className="controls-keys">
              {entry.keys.map((k, i) => (
                <span key={k} className="key-combo">
                  {i > 0 && <i className="key-sep">/</i>}
                  <kbd>{k}</kbd>
                </span>
              ))}
            </span>
            <span className="controls-label">{entry.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
