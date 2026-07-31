// 인게임 HUD. 60Hz 스냅샷을 ~10Hz 로 샘플링해서 리렌더한다.
import { memo, useEffect, useMemo, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { MAX_CHARGE } from '@/types/game';
import type { CardInfo, PlayerSnap } from '@/types/game';

const SAMPLE_MS = 100;
const SCORE_TO_WIN = 5;
const ROUNDS_TO_SCORE = 2;

/** 카드 아이콘을 보여주기 위해 지나간 available_cards 를 기억해 둔다. */
const cardCache = new Map<string, CardInfo>();

interface StoreSlice {
  playerId: string | null;
}

interface HudPlayer {
  id: string;
  nickname: string;
  color: string;
  hp: number;
  maxHp: number;
  alive: boolean;
  score: number;
  roundWins: number;
  guard: number;
  cooldown: number;
  charge: number;
  charging: boolean;
  cards: string[];
  silenced: boolean;
  poison: number;
  cold: boolean;
}

function toHudPlayer(p: PlayerSnap): HudPlayer {
  return {
    id: p.id,
    nickname: p.nickname || '익명',
    color: p.customization?.color ?? '#ff6b6b',
    hp: Math.max(0, Math.ceil(p.hp)),
    maxHp: Math.max(1, p.max_hp),
    alive: p.alive,
    score: p.score,
    roundWins: p.round_wins,
    guard: p.block_meter_max > 0 ? p.block_meter / p.block_meter_max : 0,
    cooldown: p.max_cooldown > 0 ? p.cooldown / p.max_cooldown : 0,
    charge: Math.min(1, p.charge / MAX_CHARGE),
    charging: p.charging,
    cards: p.cards,
    silenced: p.silenced,
    poison: p.poison,
    cold: p.cold,
  };
}

function useHudSample(myId: string | null): HudPlayer[] {
  const [players, setPlayers] = useState<HudPlayer[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      if (!snap) return;
      for (let i = 0; i < snap.available_cards.length; i += 1) {
        const c = snap.available_cards[i];
        if (!cardCache.has(c.id)) cardCache.set(c.id, c);
      }
      const list = snap.players.map(toHudPlayer);
      // 내가 항상 왼쪽에 오도록 정렬한다.
      if (myId) {
        const idx = list.findIndex((p) => p.id === myId);
        if (idx > 0) {
          const [me] = list.splice(idx, 1);
          list.unshift(me);
        }
      }
      setPlayers(list);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [myId]);

  return players;
}

interface MeterProps {
  ratio: number;
  color: string;
  label?: string;
}

function Meter({ ratio, color, label }: MeterProps): JSX.Element {
  const pct = `${Math.round(Math.max(0, Math.min(1, ratio)) * 100)}%`;
  return (
    <div className="hud-meter" title={label}>
      <span style={{ width: pct, background: color }} />
    </div>
  );
}

interface DotsProps {
  count: number;
  total: number;
}

function Dots({ count, total }: DotsProps): JSX.Element {
  const items = [];
  for (let i = 0; i < total; i += 1) {
    items.push(<i key={i} className={i < count ? 'hud-dot won' : 'hud-dot'} />);
  }
  return <div className="hud-dots">{items}</div>;
}

interface SideProps {
  p: HudPlayer;
  mine: boolean;
  side: 'left' | 'right';
}

function PlayerSide({ p, mine, side }: SideProps): JSX.Element {
  return (
    <div className={`hud-side ${side}${p.alive ? '' : ' dead'}`}>
      <div className="hud-name">
        <span className="hud-swatch" style={{ background: p.color }} />
        <strong>{p.nickname}</strong>
        {mine && <em className="hud-tag">나</em>}
        {p.silenced && <span title="침묵">🔇</span>}
        {p.poison > 0 && <span title="중독">🧪</span>}
        {p.cold && <span title="빙결">❄️</span>}
      </div>
      <div className="hud-hp">
        <Meter ratio={p.hp / p.maxHp} color={mine ? 'var(--accent-2)' : 'var(--accent)'} label="체력" />
        <span className="hud-hp-text">
          {p.hp}/{Math.round(p.maxHp)}
        </span>
      </div>
      <div className="hud-sub">
        <Meter ratio={p.guard} color="#4dabf7" label="가드 게이지" />
        <Meter ratio={1 - p.cooldown} color="#adb5bd" label="사격 쿨다운" />
        <Meter
          ratio={p.charge}
          color={p.charging ? '#ff2e97' : 'rgba(255,212,59,0.55)'}
          label="강공격 차징"
        />
      </div>
      <div className="hud-bottom">
        <Dots count={p.roundWins} total={ROUNDS_TO_SCORE} />
        <div className="hud-cards">
          {p.cards.map((id, i) => {
            const info = cardCache.get(id);
            return (
              <span
                key={`${id}-${i}`}
                className="hud-card"
                title={info ? `${info.name} — ${info.desc}` : id}
                style={info ? { borderColor: info.color } : undefined}
              >
                {info?.emoji ?? '🃏'}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function HudInner(): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const players = useHudSample(myId);
  const [left, right] = useMemo(() => [players[0], players[1]], [players]);

  if (!left) return null;

  return (
    <div className="hud-root">
      <PlayerSide p={left} mine={left.id === myId} side="left" />
      <div className="hud-score">
        <span className="hud-score-num">{left.score}</span>
        <span className="hud-vs">VS</span>
        <span className="hud-score-num">{right ? right.score : 0}</span>
        <div className="hud-score-hint">{SCORE_TO_WIN}점 선취</div>
      </div>
      {right ? (
        <PlayerSide p={right} mine={right.id === myId} side="right" />
      ) : (
        <div className="hud-side right waiting">상대 대기 중…</div>
      )}
    </div>
  );
}

export const Hud = memo(HudInner);
export default Hud;
