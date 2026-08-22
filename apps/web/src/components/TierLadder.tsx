// 티어 사다리 — 아이언부터 레디언트까지 계급을 한눈에.
//
// 25칸을 그대로 늘어놓으면 읽히지 않는다. **계급 단위로 묶고** 그 안의 디비전은
// 숫자로만 보여 준다(아이언 1·2·3 → "아이언  1 2 3").
//
// 이름과 색은 서버가 준 표에서만 온다(`GET /api/ranked/tiers`). 여기 적어 두면
// 계급을 하나 손대는 순간 반드시 어긋난다.
import { useEffect, useMemo, useState } from 'react';
import type { JSX } from 'react';
import RankBadge from '@/components/RankBadge';
import { loadTiers } from '@/api/ranked';
import type { TierInfo } from '@/types/ranked';
import '@/styles/ranked.css';

interface Group {
  key: string;
  name: string;
  color: string;
  /** 이 계급의 첫 티어 인덱스 — 뱃지를 그릴 때 쓴다. */
  first: number;
  divisions: number[];
}

export default function TierLadder(): JSX.Element {
  const [tiers, setTiers] = useState<TierInfo[]>([]);

  useEffect(() => {
    let alive = true;
    void loadTiers().then((list) => {
      if (alive) setTiers(list);
    });
    return () => {
      alive = false;
    };
  }, []);

  const groups = useMemo(() => {
    const out: Group[] = [];
    for (const t of tiers) {
      const last = out[out.length - 1];
      if (last && last.key === t.group) {
        if (t.division > 0) last.divisions.push(t.division);
        continue;
      }
      out.push({
        key: t.group,
        name: t.group_name,
        color: t.color,
        first: t.index,
        divisions: t.division > 0 ? [t.division] : [],
      });
    }
    return out;
  }, [tiers]);

  if (groups.length === 0) {
    return <p className="hint">티어 표를 불러오는 중…</p>;
  }

  return (
    <ol className="tier-ladder">
      {groups.map((g) => (
        <li key={g.key} style={{ ['--rank-color' as string]: g.color }}>
          {/* 계급을 대표하는 뱃지 하나. 디비전은 옆의 숫자가 말해 준다. */}
          <RankBadge tier={g.first} size={26} />
          <strong>{g.name}</strong>
          <span className="tier-divisions">
            {g.divisions.length > 0 ? g.divisions.join(' · ') : '최상위'}
          </span>
        </li>
      ))}
    </ol>
  );
}
