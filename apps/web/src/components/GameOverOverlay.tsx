// 매치 종료 오버레이. 결과를 보여주고 "REMATCH?" 를 물어본다.
// 둘 다 YES 를 누르면 서버가 곧바로 다음 매치를 시작한다(대기실을 거치지 않는다).
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
  /** 내가 YES 를 눌렀는지 (서버가 확인해 준 값) */
  iAccepted: boolean;
  /** 상대가 먼저 YES 를 눌렀는지 */
  rivalAccepted: boolean;
  /** 아직 응답이 없는 상대 이름 */
  rivalName: string;
}

const EMPTY: ResultView = {
  finished: false,
  winnerId: null,
  winnerName: '',
  score: '',
  iAccepted: false,
  rivalAccepted: false,
  rivalName: '',
};

interface GameOverOverlayProps {
  onLeave: () => void;
}

function GameOverOverlayInner({ onLeave }: GameOverOverlayProps): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const [view, setView] = useState<ResultView>(EMPTY);
  // 서버 왕복 전에 버튼이 눌린 티가 나도록 하는 낙관적 표시.
  const [voted, setVoted] = useState<'yes' | 'no' | null>(null);

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
      const accepted = snap.rematch ?? [];
      const rival = snap.players.find((p) => p.id !== myId) ?? null;
      const next: ResultView = {
        finished: true,
        winnerId: winner ? winner.id : null,
        winnerName: winner ? winner.nickname || '익명' : '무승부',
        score: snap.players.map((p) => p.score).join(' : '),
        iAccepted: myId !== null && accepted.includes(myId),
        rivalAccepted: rival !== null && accepted.includes(rival.id),
        rivalName: rival ? rival.nickname || '익명' : '상대',
      };
      setView((prev) => (sameView(prev, next) ? prev : next));
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [storePhase, myId]);

  // 매치가 끝날 때마다 투표를 새로 받는다.
  useEffect(() => {
    if (!view.finished) setVoted(null);
  }, [view.finished]);

  const vote = useCallback((accept: boolean) => {
    setVoted(accept ? 'yes' : 'no');
    if (net.isOpen()) net.send({ type: 'rematch', accept });
  }, []);

  // Y / N 단축키
  useEffect(() => {
    if (!view.finished) return undefined;
    const onKey = (e: KeyboardEvent): void => {
      if (e.repeat || e.target instanceof HTMLInputElement) return;
      const k = e.key.toLowerCase();
      if (k === 'y') vote(true);
      else if (k === 'n') vote(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view.finished, vote]);

  if (!view.finished) return null;

  const iWon = view.winnerId !== null && view.winnerId === myId;
  const waiting = view.iAccepted || voted === 'yes';

  // 이 오버레이의 문구는 참고 화면대로 영어로 통일한다.
  let status: string;
  if (waiting && view.rivalAccepted) status = 'STARTING…';
  else if (waiting) status = `WAITING FOR ${view.rivalName.toUpperCase()}`;
  else if (view.rivalAccepted) status = `${view.rivalName.toUpperCase()} WANTS A REMATCH!`;
  else status = 'BOTH PICK YES TO PLAY AGAIN';

  return (
    <div className="overlay finished">
      <p className={`result-title${iWon ? ' win' : ' lose'}`}>{iWon ? 'VICTORY' : 'DEFEAT'}</p>
      {view.winnerId && <p className="result-winner">{view.winnerName} TAKES THE MATCH</p>}
      <p className="result-score">{view.score}</p>

      <h2 className="rematch-q">REMATCH?</h2>
      <div className="rematch-choices">
        <button
          type="button"
          className={`rematch-btn yes${waiting ? ' on' : ''}`}
          onClick={() => vote(true)}
          disabled={waiting}
        >
          YES
        </button>
        <button
          type="button"
          className={`rematch-btn no${voted === 'no' ? ' on' : ''}`}
          onClick={() => vote(false)}
        >
          NO
        </button>
      </div>
      <p className="rematch-status">
        {status}
        {waiting && !view.rivalAccepted && (
          <span className="dots">
            <i />
            <i />
            <i />
          </span>
        )}
      </p>
      <p className="rematch-keys">
        or press <kbd>Y</kbd> / <kbd>N</kbd>
      </p>

      <div className="overlay-actions">
        <button type="button" className="btn btn-ghost" onClick={onLeave}>
          LEAVE
        </button>
      </div>
    </div>
  );
}

function sameView(a: ResultView, b: ResultView): boolean {
  return (
    a.finished === b.finished &&
    a.winnerId === b.winnerId &&
    a.score === b.score &&
    a.iAccepted === b.iAccepted &&
    a.rivalAccepted === b.rivalAccepted &&
    a.rivalName === b.rivalName
  );
}

export const GameOverOverlay = memo(GameOverOverlayInner);
export default GameOverOverlay;
