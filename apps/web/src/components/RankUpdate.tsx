// 매치 종료 오버레이의 랭크 변동 칸 — ±RR / 승급·강등 / 배치 진행.
//
// 이 값은 서버가 DB 에 기록을 마친 **뒤에** 오므로 매치 종료보다 한 박자 늦다.
// 그래서 아직 없을 때는 "집계 중"만 띄우고, 도착하면 게이지가 그 자리로 움직인다.
import { memo, useEffect, useState } from 'react';
import type { JSX } from 'react';
import RankBadge from '@/components/RankBadge';
import { tierOf } from '@/api/ranked';
import type { RankChange } from '@/types/ranked';

/** 게이지가 예전 값에서 새 값으로 넘어가기 전에 잠깐 멈추는 시간. */
const SETTLE_MS = 350;

interface Props {
  /** null 이면 아직 집계 중이다(경쟁전이 아니면 이 컴포넌트를 아예 그리지 않는다). */
  change: RankChange | null;
}

function RankUpdateInner({ change }: Props): JSX.Element {
  // 처음에는 변동 전 위치에 게이지를 두고, 한 박자 뒤에 새 값으로 민다.
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if (!change) {
      setSettled(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setSettled(true), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [change]);

  if (!change) {
    return (
      <div className="rank-update is-pending">
        <span className="spinner" aria-hidden />
        <span>랭크 집계 중…</span>
      </div>
    );
  }

  if (change.placement) {
    const done = change.placement_played;
    const total = change.placement_total;
    return (
      <div className="rank-update">
        <RankBadge tier={0} size={44} placement />
        <div className="rank-update-body">
          <strong>
            배치 {done} / {total}
          </strong>
          <div className="rank-meter">
            <span style={{ width: `${(done / total) * 100}%`, background: '#8b93b8' }} />
          </div>
          <span className="rank-update-note">
            {total - done}판 더 하면 티어가 정해져요.
          </span>
        </div>
      </div>
    );
  }

  const info = tierOf(change.tier_after);
  // 레디언트는 RR 상한이 없어서 100 을 넘을 수 있다.
  const target = Math.min(100, change.rr_after);
  const start = Math.min(100, change.rr_before);
  const gained = change.rr_delta > 0;

  let banner: string | null = null;
  if (change.placed_now) banner = `배치 완료 — ${info.name}`;
  else if (change.promoted) banner = `승급! ${info.name}`;
  else if (change.demoted) banner = `강등 — ${info.name}`;

  return (
    <div className={`rank-update${banner ? ' has-banner' : ''}`}>
      <RankBadge tier={change.tier_after} size={44} />
      <div className="rank-update-body">
        <strong>
          {info.name}
          <span className={`rank-delta${gained ? ' is-up' : ' is-down'}`}>
            {gained ? '+' : ''}
            {change.rr_delta} RR
          </span>
        </strong>
        <div className="rank-meter">
          <span
            style={{
              width: `${settled ? target : start}%`,
              background: info.color,
            }}
          />
        </div>
        {banner ? (
          <span className={`rank-update-note is-banner${change.demoted ? ' is-down' : ''}`}>
            {banner}
          </span>
        ) : (
          <span className="rank-update-note">{change.rr_after} / 100 RR</span>
        )}
      </div>
    </div>
  );
}

export const RankUpdate = memo(RankUpdateInner);
export default RankUpdate;
