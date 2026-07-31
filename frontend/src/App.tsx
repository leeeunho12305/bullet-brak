// 화면 라우팅: 로비 -> 대기실(waiting) -> 게임(playing/round_over/picking/finished)
import { useCallback } from 'react';
import GameScreen from '@/screens/GameScreen';
import LobbyScreen from '@/screens/LobbyScreen';
import RoomScreen from '@/screens/RoomScreen';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';

export default function App() {
  const status = useGameStore((s) => s.status);
  const phase = useGameStore((s) => s.phase);
  const room = useGameStore((s) => s.room);

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
