// 라운드 종료(2초) 표시. 이긴 쪽 색으로 문구를 띄우고, 양쪽 라운드 승수를 원으로 보여준다.
import { memo, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { LastEvent } from '@/store/gameStore';
import ScoreOrb from '@/components/ScoreOrb';
import { colorName } from '@/game/colorNames';
import { ROUNDS_TO_SCORE } from '@/types/game';
import type { Phase, PlayerSnap } from '@/types/game';

const SAMPLE_MS = 120;
const DEFAULT_COLOR = '#ff6b6b';

interface StoreSlice {
  playerId: string | null;
  phase: Phase;
  lastEvent: LastEvent | null;
}

/** 원이 얼마나 커지는지. 캔버스가 작을 땐 vw 에 맞춰 줄어든다. */
const ORB_SIZE = 'clamp(96px, 21vw, 190px)';

interface OrbView {
  id: string;
  nickname: string;
  color: string;
  wins: number;
  /** 이번 라운드를 이겨서 방금 차오른 원인가 */
  won: boolean;
}

interface RoundView {
  /** 리렌더 판정용 서명 */
  key: string;
  /** "HALF BLUE" / "POINT BLUE" / "DRAW" */
  title: string;
  /** 이긴 팀 색. 제목 글로우에 쓴다(글자 자체는 흰색). */
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
  const winnerId = winnerIdOf(players, ev);
  const orbs: OrbView[] = list.map((p) => ({
    id: p.id,
    nickname: p.nickname || '익명',
    color: colorOf(p),
    wins: p.round_wins,
    won: p.id === winnerId,
  }));

  // 이긴 팀을 닉네임이 아니라 "색"으로 부른다 — 원의 색과 문구가 바로 이어진다.
  // 1승이면 원이 반만 차니까 HALF, 2승째면 원이 꽉 차고 점수가 난다.
  const winner = players.find((p) => p.id === winnerId) ?? null;
  const scored = winner !== null && winner.round_wins >= ROUNDS_TO_SCORE;
  const title = winner
    ? `${scored ? 'POINT' : 'HALF'} ${colorName(colorOf(winner))}`
    : 'DRAW';
  const color = winner ? colorOf(winner) : 'var(--muted)';
  const key = `${title}|${orbs.map((o) => `${o.id}:${o.wins}:${o.color}:${o.won ? 1 : 0}`).join(',')}`;
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
      {/* 글자는 흰색이고 글로우만 이긴 팀 색이다(어느 색이 이겨도 잘 읽힌다). */}
      <h3
        className="round-result-title"
        style={{ textShadow: `0 0 28px ${view.color}, 0 0 68px ${view.color}` }}
      >
        {view.title}
      </h3>
      {/* 양쪽 화면에 똑같이 뜬다. 라벨 없이 원만 — 색이 곧 이름이다. */}
      <div className="round-result-orbs">
        {view.orbs.map((o) => (
          <div
            key={o.id}
            className={`round-orb${o.won ? ' won' : ''}`}
            aria-label={`${o.nickname}: ${o.wins}/${ROUNDS_TO_SCORE}`}
          >
            <ScoreOrb wins={o.wins} color={o.color} size={ORB_SIZE} />
          </div>
        ))}
      </div>
    </div>
  );
}

export const RoundResult = memo(RoundResultInner);
export default RoundResult;
