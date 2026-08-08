// Tab 을 누르고 있는 동안만 좌측 상단에 뜨는 정보 패널.
// 거리별 대미지 / 내 스탯 요약 / 보유 카드. 숫자는 전부 서버가 계산한 값이다.
import { useEffect, useMemo, useRef, useState } from 'react';
import type { JSX } from 'react';
import { api } from '@/api/client';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { CardInfo, DamageRow, PlayerSnap, PlayerStats } from '@/types/game';

const SAMPLE_MS = 250; // 열려 있는 동안에만 샘플링

interface Panel {
  table: DamageRow[];
  stats: PlayerStats | null;
  cards: string[];
}

const EMPTY: Panel = { table: [], stats: null, cards: [] };

const STAT_ROWS: { key: keyof PlayerStats; label: string; suffix?: string }[] = [
  { key: 'damage_mult', label: '공격력', suffix: '×' },
  { key: 'max_hp', label: '최대 체력' },
  { key: 'cooldown', label: '쿨다운', suffix: '틱' },
  { key: 'shots_per_fire', label: '발사 수', suffix: '발' },
  { key: 'bullet_speed', label: '탄속' },
  { key: 'bullet_size', label: '탄 크기' },
  { key: 'bounces', label: '도탄', suffix: '회' },
  { key: 'knockback', label: '넉백', suffix: '×' },
  { key: 'speed', label: '이동 속도' },
  { key: 'block_uses', label: '가드 횟수', suffix: '회/라운드' },
  { key: 'block_seconds', label: '가드 지속', suffix: '초' },
];

/** 같은 값이면 setState 를 건너뛰기 위한 얕은 비교 */
function samePanel(a: Panel, b: Panel): boolean {
  if (a.stats !== b.stats && JSON.stringify(a.stats) !== JSON.stringify(b.stats)) return false;
  if (a.cards.length !== b.cards.length || a.cards.some((c, i) => c !== b.cards[i])) return false;
  if (a.table.length !== b.table.length) return false;
  return a.table.every((row, i) => row.damage === b.table[i]?.damage);
}

export default function InfoPanel(): JSX.Element | null {
  const playerId = useGameStore((s: { playerId: string | null }) => s.playerId);
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>(EMPTY);
  const [catalog, setCatalog] = useState<Record<string, CardInfo>>({});
  const openRef = useRef(false);

  // 카드 도감은 한 번만 받아 둔다(이름/이모지/설명 표시용).
  useEffect(() => {
    let alive = true;
    api
      .getCards()
      .then((list) => {
        if (!alive) return;
        const map: Record<string, CardInfo> = {};
        for (const card of list) map[card.id] = card;
        setCatalog(map);
      })
      .catch(() => {
        /* 도감을 못 받으면 카드 id 를 그대로 보여준다 */
      });
    return () => {
      alive = false;
    };
  }, []);

  // Tab 홀드. 브라우저 포커스 이동을 막아야 해서 preventDefault 필수.
  useEffect(() => {
    const typing = (): boolean => {
      const el = document.activeElement;
      return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
    };
    const down = (e: KeyboardEvent): void => {
      if (e.code !== 'Tab' || typing()) return;
      e.preventDefault();
      if (!openRef.current) {
        openRef.current = true;
        setOpen(true);
      }
    };
    const up = (e: KeyboardEvent): void => {
      if (e.code !== 'Tab') return;
      e.preventDefault();
      openRef.current = false;
      setOpen(false);
    };
    const blur = (): void => {
      openRef.current = false;
      setOpen(false);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, []);

  // 열려 있는 동안만 스냅샷에서 내 정보를 뽑는다.
  useEffect(() => {
    if (!open) return;
    const read = (): void => {
      const snap = net.latest;
      const me: PlayerSnap | undefined = snap?.players.find((p) => p.id === playerId);
      if (!me) {
        setPanel((prev) => (prev === EMPTY ? prev : EMPTY));
        return;
      }
      // stats/damage_table 은 0.5초에 한 번만 오므로 없으면 직전 값을 유지한다.
      setPanel((prev) => {
        const next: Panel = {
          table: me.damage_table ?? prev.table,
          stats: me.stats ?? prev.stats,
          cards: me.cards,
        };
        return samePanel(prev, next) ? prev : next;
      });
    };
    read();
    const timer = window.setInterval(read, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [open, playerId]);

  const maxDamage = useMemo(
    () => panel.table.reduce((acc, row) => Math.max(acc, row.damage), 1),
    [panel.table],
  );

  if (!open) return null;

  return (
    <aside className="info-panel" aria-label="플레이어 정보">
      <section className="info-block">
        <h3 className="info-title">거리별 대미지</h3>
        <table className="info-table">
          <tbody>
            {panel.table.map((row) => (
              <tr key={row.distance}>
                <th scope="row">{row.distance}px</th>
                <td>
                  <span className="info-bar" style={{ width: `${(row.damage / maxDamage) * 100}%` }} />
                </td>
                <td className="info-num">{row.damage.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="info-foot">가까울수록 강함 · 600px 이상은 동일</p>
      </section>

      <section className="info-block">
        <h3 className="info-title">내 스탯</h3>
        <dl className="info-stats">
          {panel.stats &&
            STAT_ROWS.map(({ key, label, suffix }) => (
              <div key={key} className="info-stat">
                <dt>{label}</dt>
                <dd>
                  {panel.stats?.[key]}
                  {suffix ?? ''}
                </dd>
              </div>
            ))}
        </dl>
      </section>

      <section className="info-block">
        <h3 className="info-title">보유 카드 ({panel.cards.length})</h3>
        {panel.cards.length === 0 ? (
          <p className="info-empty">아직 없음 — 라운드에서 지면 고를 수 있습니다</p>
        ) : (
          <ul className="info-cards">
            {panel.cards.map((id, i) => {
              const card = catalog[id];
              return (
                <li key={`${id}-${i}`} style={{ borderLeftColor: card?.color ?? 'var(--line)' }}>
                  <span className="info-card-name">
                    {card?.emoji ?? '🃏'} {card?.name ?? id}
                  </span>
                  {card && <span className="info-card-desc">{card.desc}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </aside>
  );
}
