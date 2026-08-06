// 라운드 종료(2초) 표시. 이긴 쪽 색으로 문구를 띄우고, 양쪽 라운드 승수를 원으로 보여준다.
import { memo, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { LastEvent } from '@/store/gameStore';
import ScoreOrb from '@/components/ScoreOrb';
import { ROUNDS_TO_SCORE } from '@/types/game';
import type { Phase, PlayerSnap } from '@/types/game';

const SAMPLE_MS = 120;
const DEFAULT_COLOR = '#ff6b6b';

interface StoreSlice {
  playerId: string | null;
  phase: Phase;
  lastEvent: LastEvent | null;
}

interface OrbView {
  id: string;
  nickname: string;
  color: string;
  wins: number;
}

interface RoundView {
  /** 리렌더 판정용 서명 */
  key: string;
  title: string;
  color: string;
  orbs: OrbView[];
}

function colorOf(p: PlayerSnap): string {
  return p.customization?.color ?? DEFAULT_COLOR;
}

/**
 * 라운드 승자. 스냅샷의 winner_id 는 매치가 끝나야 채워지므로 event 를 먼저 본다.
 * (재접속 등으로 event 를 놓쳤으면 살아남은 한 명으로 대신 판정한다.)
 */
function winnerIdOf(players: PlayerSnap[], ev: LastEvent | null): string | null {
  if (ev && ev.event === 'round_over') return ev.winner_id;
  const alive = players.filter((p) => p.alive);
  return alive.length === 1 ? alive[0].id : null;
}

function buildView(players: PlayerSnap[], ev: LastEvent | null, myId: string | null): RoundView {
  // HUD 와 좌우를 맞춘다(내가 항상 왼쪽).
  const list = [...players];
  if (myId) {
    const idx = list.findIndex((p) => p.id === myId);
    if (idx > 0) list.unshift(...list.splice(idx, 1));
  }
  const orbs: OrbView[] = list.map((p) => ({
    id: p.id,
    nickname: p.nickname || 'Guest',
    color: colorOf(p),
    wins: p.round_wins,
  }));

  // 참고 화면대로 "HALF <이긴 쪽>" / 2승째면 "POINT <이긴 쪽>".
  const winner = players.find((p) => p.id === winnerIdOf(players, ev)) ?? null;
  const title = winner
    ? `${winner.round_wins >= ROUNDS_TO_SCORE ? 'POINT' : 'HALF'} ${(winner.nickname || 'GUEST').toUpperCase()}`
    : 'DRAW';
  const color = winner ? colorOf(winner) : 'var(--muted)';
  const key = `${title}|${orbs.map((o) => `${o.id}:${o.wins}:${o.color}`).join(',')}`;
  return { key, title, color, orbs };
}

function RoundResultInner(): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const lastEvent = useGameStore((s: StoreSlice) => s.lastEvent);
  const [view, setView] = useState<RoundView | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      const phase: Phase = snap ? snap.phase : storePhase;
      if (phase !== 'round_over' || !snap) {
        setView((prev) => (prev ? null : prev));
        return;
      }
      const next = buildView(snap.players, lastEvent, myId);
      setView((prev) => (prev && prev.key === next.key ? prev : next));
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [storePhase, lastEvent, myId]);

  if (!view) return null;

  return (
    <div className="round-result">
      <h3 className="round-result-title" style={{ color: view.color }}>
        {view.title}
      </h3>
      <div className="round-result-orbs">
        {view.orbs.map((o) => (
          <div key={o.id} className="round-orb">
            <ScoreOrb wins={o.wins} color={o.color} size={64} />
            <span className="round-orb-name" style={{ color: o.color }}>
              {o.nickname}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export const RoundResult = memo(RoundResultInner);
export default RoundResult;
