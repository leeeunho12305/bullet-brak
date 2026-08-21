// 인게임 화면 조립: 캔버스 + HUD + 오버레이 + 채팅.
import { useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { useInput } from '@/game/useInput';
import { useFullscreen } from '@/hooks/useFullscreen';
import GameCanvas from '@/components/GameCanvas';
import Hud from '@/components/Hud';
import CardPicker from '@/components/CardPicker';
import ChatBox from '@/components/ChatBox';
import GameOverOverlay from '@/components/GameOverOverlay';
import RoundResult from '@/components/RoundResult';
import InfoPanel from '@/components/InfoPanel';
import PlayerLeftNotice from '@/components/PlayerLeftNotice';
import type { Phase, RoomState } from '@/types/game';
import '@/styles/game.css';
import '@/styles/overlay.css';

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

// 조작키 전체 안내는 로비(ControlsGuide)로 옮겼다 — 캔버스를 가리지 않게.
const CONTROLS = 'Tab: 정보 보기';

export default function GameScreen({ onLeave }: { onLeave: () => void }): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const playerId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const room = useGameStore((s: StoreSlice) => s.room);
  const [banner, setBanner] = useState<BannerState>({ phase: storePhase, text: '' });

  // 캔버스 구석 버튼으로 켜고 끈다. 대기실로 돌아가면 이 요소가 사라지면서
  // 브라우저가 전체화면을 알아서 푼다.
  const rootRef = useRef<HTMLDivElement | null>(null);
  const fullscreen = useFullscreen(rootRef);

  useInput(canvasRef, { enabled: banner.phase === 'playing', myId: playerId });

  // 페이즈 배너는 저빈도로만 갱신한다(라운드 종료는 RoundResult 가 맡는다).
  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      const phase: Phase = snap ? snap.phase : storePhase;
      const text = phase === 'waiting' ? '상대 플레이어를 기다리는 중…' : '';
      setBanner((prev) => (prev.phase === phase && prev.text === text ? prev : { phase, text }));
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [storePhase]);

  // 소켓 종료/상태 초기화는 App 의 onLeave 가 담당한다.
  const handleLeave = (): void => {
    onLeave();
  };

  return (
    <div ref={rootRef} className={`game-screen${fullscreen.active ? ' is-fullscreen' : ''}`}>
      <header className="game-topbar">
        <div className="game-room">
          <span className="game-room-code">{room ? `방 ${room.code}` : '연결 중…'}</span>
          <span className="game-room-mode">{room?.mode === 'training' ? '훈련장' : '대전'}</span>
          {room?.map ? (
            <span className="game-room-map" title={room.map.desc}>
              {room.map.emoji} {room.map.name}
            </span>
          ) : null}
        </div>
        <p className="game-controls">{CONTROLS}</p>
        <button type="button" className="btn btn-ghost" onClick={handleLeave}>
          나가기
        </button>
      </header>

      <div className="game-body">
        <div className="game-stage">
          <Hud />
          {/* 남는 공간을 재는 상자. 전체화면에서 캔버스가 16:9 를 지킨 채 최대로 커지는 기준이 된다. */}
          <div className="game-canvas-area">
            <div className="game-canvas-wrap">
              <GameCanvas canvasRef={canvasRef} />
              {/* 캔버스 오른쪽 위 구석의 전체화면 토글 (Esc 로도 빠져나온다) */}
              {fullscreen.supported ? (
                <button
                  type="button"
                  className="game-fs-btn"
                  onClick={fullscreen.toggle}
                  title={fullscreen.active ? 'Leave fullscreen (Esc)' : 'Play in fullscreen'}
                  aria-label={fullscreen.active ? 'Leave fullscreen' : 'Play in fullscreen'}
                >
                  {fullscreen.active ? '⤡' : '⛶'}
                </button>
              ) : null}
              {banner.text && <div className="game-banner">{banner.text}</div>}
              <RoundResult />
              <InfoPanel />
              <CardPicker />
              <GameOverOverlay onLeave={handleLeave} />
              {/* 3~4인 방에서는 한 명이 나가도 경기가 이어진다 — 캔버스 위에 토스트로 알린다 */}
              <PlayerLeftNotice variant="game" />
            </div>
          </div>
        </div>
        <ChatBox />
      </div>
    </div>
  );
}
