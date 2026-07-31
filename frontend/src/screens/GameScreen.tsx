// 인게임 화면 조립: 캔버스 + HUD + 오버레이 + 채팅.
import { useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { useInput } from '@/game/useInput';
import GameCanvas from '@/components/GameCanvas';
import Hud from '@/components/Hud';
import CardPicker from '@/components/CardPicker';
import ChatBox from '@/components/ChatBox';
import GameOverOverlay from '@/components/GameOverOverlay';
import type { Phase, RoomState } from '@/types/game';
import '@/styles/game.css';

const SAMPLE_MS = 200;

interface StoreSlice {
  playerId: string | null;
  phase: Phase;
  room: RoomState | null;
}

interface BannerState {
  phase: Phase;
  text: string;
}

const CONTROLS = 'A/D 이동 · W·Space 점프 · 마우스 조준 · 좌클릭 사격 · 길게 누르기/E 강공격 · 우클릭·Shift 가드 · Enter 채팅';

export default function GameScreen({ onLeave }: { onLeave: () => void }): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const playerId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const room = useGameStore((s: StoreSlice) => s.room);
  const [banner, setBanner] = useState<BannerState>({ phase: storePhase, text: '' });

  useInput(canvasRef, { enabled: banner.phase === 'playing', myId: playerId });

  // 페이즈/라운드 배너는 저빈도로만 갱신한다.
  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      const phase: Phase = snap ? snap.phase : storePhase;
      let text = '';
      if (phase === 'waiting') {
        text = '상대 플레이어를 기다리는 중…';
      } else if (phase === 'round_over' && snap) {
        const winner = snap.players.find((p) => p.id === snap.winner_id);
        text = winner ? `${winner.nickname || '익명'} 라운드 승리!` : '라운드 종료!';
      }
      setBanner((prev) => (prev.phase === phase && prev.text === text ? prev : { phase, text }));
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [storePhase]);

  const handleLeave = (): void => {
    net.disconnect();
    onLeave();
  };

  return (
    <div className="game-screen">
      <header className="game-topbar">
        <div className="game-room">
          <span className="game-room-code">{room ? `방 ${room.code}` : '연결 중…'}</span>
          <span className="game-room-mode">{room?.mode === 'training' ? '훈련장' : '대전'}</span>
        </div>
        <p className="game-controls">{CONTROLS}</p>
        <button type="button" className="btn btn-ghost" onClick={handleLeave}>
          나가기
        </button>
      </header>

      <div className="game-body">
        <div className="game-stage">
          <Hud />
          <div className="game-canvas-wrap">
            <GameCanvas canvasRef={canvasRef} />
            {banner.text && <div className="game-banner">{banner.text}</div>}
            <CardPicker />
            <GameOverOverlay onLeave={handleLeave} />
          </div>
        </div>
        <ChatBox />
      </div>
    </div>
  );
}
