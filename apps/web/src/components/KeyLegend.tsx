// 화면 하단 반투명 조작키 안내. 정보 패널(Tab)도 여기서 알려준다.
import type { JSX } from 'react';

interface Entry {
  keys: string[];
  label: string;
  highlight?: boolean;
}

const ENTRIES: Entry[] = [
  { keys: ['A', 'D'], label: 'Move' },
  { keys: ['W', 'Space'], label: 'Jump' },
  { keys: ['Mouse'], label: 'Aim' },
  { keys: ['L-Click'], label: 'Shoot' },
  { keys: ['Hold L-Click', 'E'], label: 'Heavy shot' },
  { keys: ['R-Click', 'Shift'], label: 'Block' },
  { keys: ['Enter'], label: 'Chat' },
  { keys: ['Tab'], label: 'Stats', highlight: true },
];

export default function KeyLegend(): JSX.Element {
  return (
    <div className="key-legend" aria-label="Controls">
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
