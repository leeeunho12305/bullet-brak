// 화면 하단 반투명 조작키 안내. 정보 패널(Tab)도 여기서 알려준다.
import type { JSX } from 'react';

interface Entry {
  keys: string[];
  label: string;
  highlight?: boolean;
}

const ENTRIES: Entry[] = [
  { keys: ['A', 'D'], label: '이동' },
  { keys: ['W', 'Space'], label: '점프' },
  { keys: ['마우스'], label: '조준' },
  { keys: ['좌클릭'], label: '사격' },
  { keys: ['좌클릭 길게', 'E'], label: '강공격' },
  { keys: ['우클릭', 'Shift'], label: '가드' },
  { keys: ['Enter'], label: '채팅' },
  { keys: ['Tab'], label: '정보 보기', highlight: true },
];

export default function KeyLegend(): JSX.Element {
  return (
    <div className="key-legend" aria-label="조작키 안내">
      {ENTRIES.map((entry) => (
        <span
          key={entry.label}
          className={entry.highlight ? 'key-entry key-entry-hl' : 'key-entry'}
        >
          {entry.keys.map((k, i) => (
            <span key={k} className="key-combo">
              {i > 0 && <i className="key-sep">/</i>}
              <kbd>{k}</kbd>
            </span>
          ))}
          <span className="key-label">{entry.label}</span>
        </span>
      ))}
    </div>
  );
}
