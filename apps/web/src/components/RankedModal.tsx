// 순위표 + 전적 모달.
//
// 두 탭 다 **열 때 한 번만** 읽는다. 랭크는 매치가 끝나야 바뀌는 값이라 폴링할 이유가
// 없고, 로비에서 초당 몇 번씩 순위표를 긁으면 그게 곧 서버 부하다.
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import RankBadge from '@/components/RankBadge';
import RankPanel from '@/components/RankPanel';
import { fetchLeaderboard, fetchMatches, tierOf, winRate } from '@/api/ranked';
import { useGameStore } from '@/store/gameStore';
import type { LeaderboardEntry, MatchRecord } from '@/types/ranked';

type Tab = 'board' | 'history';

interface Props {
  onClose(): void;
}

export default function RankedModal({ onClose }: Props): JSX.Element {
  const accountId = useGameStore((s) => s.accountId);
  const myRank = useGameStore((s) => s.myRank);
  const seasonName = myRank?.season.name ?? '경쟁전';

  const [tab, setTab] = useState<Tab>('board');
  const [board, setBoard] = useState<LeaderboardEntry[] | null>(null);
  const [history, setHistory] = useState<MatchRecord[] | null>(null);

  // Esc 로 닫는다(다른 모달과 같은 규칙).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    if (tab === 'board' && board === null) {
      void fetchLeaderboard(50).then((page) => {
        if (alive) setBoard(page?.entries ?? []);
      });
    }
    if (tab === 'history' && history === null) {
      void fetchMatches(20, false).then((rows) => {
        if (alive) setHistory(rows);
      });
    }
    return () => {
      alive = false;
    };
  }, [tab, board, history]);

  const switchTab = useCallback((next: Tab) => setTab(next), []);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="경쟁전 기록">
      <div className="modal">
        <div className="modal-head">
          <h2>
            🏆 {seasonName}
            <span className="muted">{tab === 'board' ? '순위표' : '내 전적'}</span>
          </h2>
          <button type="button" className="btn btn-ghost modal-x" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          <div className="account-tabs ranked-tabs">
            <button
              type="button"
              className={`btn${tab === 'board' ? ' is-on' : ''}`}
              onClick={() => switchTab('board')}
            >
              순위표
            </button>
            <button
              type="button"
              className={`btn${tab === 'history' ? ' is-on' : ''}`}
              onClick={() => switchTab('history')}
            >
              내 전적
            </button>
          </div>

          {tab === 'board' ? (
            <>
              {/* 로비에서 뺀 자세한 성적(승률·연승·최고 티어)을 여기로 옮겼다. */}
              {myRank ? <RankPanel rank={myRank} /> : null}
              <Leaderboard entries={board} meId={accountId} />
            </>
          ) : (
            <History rows={history} />
          )}
        </div>

        <div className="modal-foot">
          <p className="hint">
            {tab === 'board'
              ? '배치 5판을 마쳐야 순위표에 올라가요.'
              : '경쟁전은 RR 변동이, 일반전은 결과만 남아요.'}
          </p>
          <button type="button" className="btn" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

function Leaderboard({
  entries,
  meId,
}: {
  entries: LeaderboardEntry[] | null;
  meId: string | null;
}): JSX.Element {
  if (entries === null) return <p className="hint">불러오는 중…</p>;
  if (entries.length === 0) {
    return <p className="hint">아직 배치를 마친 사람이 없어요. 첫 랭커가 되어 보세요!</p>;
  }

  return (
    <ol className="rank-board">
      {entries.map((entry) => (
        <li
          key={entry.account_id}
          className={`rank-row${entry.account_id === meId ? ' is-me' : ''}`}
        >
          <span className="rank-pos">{entry.position}</span>
          <RankBadge tier={entry.rank.tier} size={26} />
          <span className="rank-who">
            <strong>{entry.nickname || '익명'}</strong>
            <span className="muted">{tierOf(entry.rank.tier).name}</span>
          </span>
          <span className="rank-rr">
            {entry.rank.rr} <small>RR</small>
          </span>
          <span className="rank-wl muted">
            {entry.rank.wins}승 {entry.rank.losses}패 · {winRate(entry.rank)}%
          </span>
        </li>
      ))}
    </ol>
  );
}

function History({ rows }: { rows: MatchRecord[] | null }): JSX.Element {
  if (rows === null) return <p className="hint">불러오는 중…</p>;
  if (rows.length === 0) return <p className="hint">아직 기록된 매치가 없어요.</p>;

  return (
    <ul className="match-list">
      {rows.map((row) => (
        <li key={row.id} className={`match-row${row.won ? ' is-win' : ' is-loss'}`}>
          <span className="match-result">{row.won ? '승' : '패'}</span>
          <span className="match-main">
            <strong>
              {row.score} : {row.opponent_score}
            </strong>
            <span className="muted">
              vs {row.opponent_nickname}
              {row.forfeit ? ' (탈주)' : ''}
            </span>
          </span>
          <span className="match-meta">
            <span className={`match-tag${row.ranked ? ' is-ranked' : ''}`}>
              {row.ranked ? '경쟁' : '일반'}
            </span>
            <span className="muted">{formatWhen(row.ended_at)}</span>
          </span>
          <span className="match-rr">{rrText(row)}</span>
        </li>
      ))}
    </ul>
  );
}

/** 전적 줄 오른쪽의 RR 칸. 일반전은 비우고, 배치전은 판수를 보여 준다. */
function rrText(row: MatchRecord): string {
  if (!row.ranked) return '';
  if (row.placement) return '배치';
  return row.rr_delta > 0 ? `+${row.rr_delta}` : `${row.rr_delta}`;
}

/** "3분 전" / "어제" / "8월 20일". 초 단위까지 볼 이유가 없는 목록이다. */
function formatWhen(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.floor((Date.now() - then) / 60000);
  if (minutes < 1) return '방금';
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  if (hours < 48) return '어제';
  return new Date(then).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
}
