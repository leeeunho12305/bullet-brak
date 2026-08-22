// 화면 라우팅: 로비 -> 대기실(waiting) -> 게임(playing/round_over/picking/finished)
import { useCallback, useEffect } from 'react';
import GameScreen from '@/screens/GameScreen';
import LobbyScreen from '@/screens/LobbyScreen';
import RoomScreen from '@/screens/RoomScreen';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { bootstrapIdentity } from '@/api/identity';
import { loadTiers } from '@/api/ranked';
import { loadOwnedItems } from '@/hooks/useLocalProfile';

/**
 * 첫 실행에 디바이스 토큰을 확보하고 계정을 프로필에 반영한다.
 *
 * 실패해도(서버에 DB 가 없거나 오프라인) 아무 일도 일어나지 않는다 —
 * accountId 가 null 로 남고 게임은 예전처럼 localStorage 만으로 돈다.
 */
function useIdentity(): void {
  useEffect(() => {
    let cancelled = false;
    const store = useGameStore.getState();

    void bootstrapIdentity({
      nickname: store.nickname,
      customization: store.customization,
      // 최초 1회만 넘어가는 이관 값. 서버가 상한으로 자른다.
      coins: store.coins,
      ownedItems: Object.keys(loadOwnedItems()),
    }).then((account) => {
      if (cancelled) return;
      const state = useGameStore.getState();
      if (!account) {
        state.markLocalOnly();
        return;
      }
      state.applyAccount(account);
      // 뱃지 색·이름의 원본은 서버다. 랭크 카드보다 먼저 받아 두면 깜빡이지 않는다.
      void loadTiers().then(() => useGameStore.getState().refreshRank());
    });

    return () => {
      cancelled = true;
    };
  }, []);
}

export default function App() {
  const status = useGameStore((s) => s.status);
  const phase = useGameStore((s) => s.phase);
  const room = useGameStore((s) => s.room);

  useIdentity();

  /** 방 나가기: 소켓 종료 + 세션 상태 초기화(프로필은 유지) */
  const leave = useCallback(() => {
    net.disconnect();
    useGameStore.getState().reset();
  }, []);

  if (status === 'connected' && room) {
    // 훈련 모드는 대기실을 거치지 않는다.
    const inGame = phase !== 'waiting' || room.mode === 'training';
    if (inGame) return <GameScreen onLeave={leave} />;
    return (
      <div className="app-shell">
        <RoomScreen onLeave={leave} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <LobbyScreen />
    </div>
  );
}
