// "상대방이 나갔습니다" 알림. 서버의 player_left 메시지로만 뜬다.
// 상대가 나가면 서버가 매치를 접고 대기실로 되돌리기 때문에, 알림이 없으면
// 화면이 갑자기 바뀐 이유를 알 수 없다.
import { memo, useEffect } from 'react';
import type { JSX } from 'react';
import { useGameStore } from '@/store/gameStore';
import type { PlayerLeft } from '@/store/gameStore';

/** 알림이 저절로 사라지기까지 */
const AUTO_HIDE_MS = 7000;

interface Props {
  /** 'room' = 대기실 패널 안, 'game' = 캔버스 위에 띄우는 토스트 */
  variant?: 'room' | 'game';
}

function PlayerLeftNoticeInner({ variant = 'room' }: Props): JSX.Element | null {
  const left = useGameStore((s) => s.playerLeft) as PlayerLeft | null;
  const clear = useGameStore((s) => s.clearPlayerLeft);

  useEffect(() => {
    if (!left) return undefined;
    const timer = window.setTimeout(clear, AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [left, clear]);

  if (!left) return null;

  return (
    <div className={`left-notice ${variant}`} role="status">
      <span className="left-notice-icon" aria-hidden>
        👋
      </span>
      <span className="left-notice-body">
        <strong>Your opponent left</strong>
        <span className="left-notice-sub">
          {left.nickname} left the room.
          {left.playersLeft < 2 ? ' You can start again once someone else joins.' : ''}
        </span>
      </span>
      <button type="button" className="left-notice-close" aria-label="Dismiss" onClick={clear}>
        ✕
      </button>
    </div>
  );
}

export const PlayerLeftNotice = memo(PlayerLeftNoticeInner);
export default PlayerLeftNotice;
