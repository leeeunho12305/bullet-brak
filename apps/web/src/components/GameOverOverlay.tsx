// 매치 종료 오버레이. 승자 표시 + 다시하기 / 나가기.
import { memo, useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { Phase } from '@/types/game';

const SAMPLE_MS = 200;

interface StoreSlice {
  playerId: string | null;
  phase: Phase;
}

interface ResultView {
  finished: boolean;
  winnerId: string | null;
  winnerName: string;
  score: string;
}

const EMPTY: ResultView = { finished: false, winnerId: null, winnerName: '', score: '' };

interface GameOverOverlayProps {
  onLeave: () => void;
}

function GameOverOverlayInner({ onLeave }: GameOverOverlayProps): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const [view, setView] = useState<ResultView>(EMPTY);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      const phase = snap ? snap.phase : storePhase;
      if (phase !== 'finished' || !snap) {
        setView((prev) => (prev.finished ? EMPTY : prev));
        return;
      }
      let winner = snap.players.find((p) => p.id === snap.winner_id) ?? null;
      if (!winner && snap.players.length > 0) {
        winner = snap.players.reduce((a, b) => (a.score >= b.score ? a : b));
      }
      const score = snap.players.map((p) => p.score).join(' : ');
      const next: ResultView = {
        finished: true,
        winnerId: winner ? winner.id : null,
        winnerName: winner ? winner.nickname || '익명' : '무승부',
        score,
      };
      setView((prev) =>
        prev.finished && prev.winnerId === next.winnerId && prev.score === next.score ? prev : next,
      );
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [storePhase]);

  const onRestart = useCallback(() => {
    if (net.isOpen()) net.send({ type: 'restart' });
  }, []);

  if (!view.finished) return null;
  const iWon = view.winnerId !== null && view.winnerId === myId;

  return (
    <div className="overlay finished">
      <h2 className={`result-title${iWon ? ' win' : ' lose'}`}>{iWon ? '승리!' : '패배'}</h2>
      <p className="result-winner">{view.winnerName} 님이 매치를 가져갔습니다</p>
      <p className="result-score">{view.score}</p>
      <div className="overlay-actions">
        <button type="button" className="btn btn-primary" onClick={onRestart}>
          다시하기
        </button>
        <button type="button" className="btn btn-ghost" onClick={onLeave}>
          나가기
        </button>
      </div>
    </div>
  );
}

export const GameOverOverlay = memo(GameOverOverlayInner);
export default GameOverOverlay;
