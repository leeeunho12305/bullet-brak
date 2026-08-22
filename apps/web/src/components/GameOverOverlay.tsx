// 매치 종료 오버레이. 결과를 보여주고 "REMATCH?" 를 물어본다.
// 둘 다 YES 를 누르면 서버가 곧바로 다음 매치를 시작한다(대기실을 거치지 않는다).
import { memo, useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import RankUpdate from '@/components/RankUpdate';
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
  /** 다시 하기를 누른 사람 수 */
  accepted: number;
  /** 방에 있는 사람 수(=다 눌러야 하는 수) */
  total: number;
}

const EMPTY: ResultView = {
  finished: false,
  winnerId: null,
  winnerName: '',
  score: '',
  iAccepted: false,
  rivalAccepted: false,
  rivalName: '',
  accepted: 0,
  total: 0,
};

interface GameOverOverlayProps {
  onLeave: () => void;
}

function GameOverOverlayInner({ onLeave }: GameOverOverlayProps): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  // 경쟁전이면 RR 변동 칸을 띄운다. 값은 서버가 기록을 마친 뒤에 도착하므로
  // 그전까지는 rankChange 가 null 이고 RankUpdate 가 "집계 중"을 보여 준다.
  const isRanked = useGameStore((s) => s.room?.ranked ?? false);
  const rankChange = useGameStore((s) => s.rankChange);
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
        winnerName: winner ? winner.nickname || 'Guest' : 'Draw',
        score: snap.players.map((p) => p.score).join(' : '),
        iAccepted: myId !== null && accepted.includes(myId),
        rivalAccepted: rival !== null && accepted.includes(rival.id),
        rivalName: rival ? rival.nickname || 'Guest' : 'your opponent',
        accepted: accepted.length,
        total: snap.players.length,
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
  // 서버 왕복(최대 200ms 샘플링) 전에도 내 표는 즉시 세어 준다.
  const acceptedCount = Math.max(view.accepted, waiting ? 1 : 0);
  const totalCount = Math.max(view.total, 2);

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

      {isRanked ? <RankUpdate change={rankChange} /> : null}

      <h2 className="rematch-q">REMATCH?</h2>
      <div className="rematch-choices">
        <span className="rematch-yes-wrap">
          <button
            type="button"
            className={`rematch-btn yes${waiting ? ' on' : ''}`}
            onClick={() => vote(true)}
            disabled={waiting}
          >
            YES
          </button>
          {/* 몇 명이 눌렀는지. 누른 사람은 여기를 보고 기다린다. */}
          {acceptedCount > 0 && (
            <span
              className={`rematch-count${acceptedCount >= totalCount ? ' full' : ''}`}
              aria-label={`${acceptedCount} of ${totalCount} players want a rematch`}
            >
              {acceptedCount}/{totalCount}
            </span>
          )}
        </span>
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
    a.rivalName === b.rivalName &&
    a.accepted === b.accepted &&
    a.total === b.total
  );
}

export const GameOverOverlay = memo(GameOverOverlayInner);
export default GameOverOverlay;
