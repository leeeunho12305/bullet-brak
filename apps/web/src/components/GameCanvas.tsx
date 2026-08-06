// 800x600 고정 좌표계 캔버스(백버퍼는 표시 크기에 맞춰 늘린다).
// rAF 루프에서 net.latest 를 직접 읽는다(React state 사용 금지).
import { memo, useEffect, useRef } from 'react';
import type { JSX, RefObject } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { backgroundColor, renderFrame, resetInterpolation, setMapTheme } from '@/game/renderer';
import { WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { MapTheme, Phase, RoomState } from '@/types/game';

interface StoreSlice {
  playerId: string | null;
  room: RoomState | null;
}

interface GameCanvasProps {
  canvasRef: RefObject<HTMLCanvasElement | null>;
}

function GameCanvasInner({ canvasRef }: GameCanvasProps): JSX.Element {
  const playerId = useGameStore((s: StoreSlice) => s.playerId);
  const playerIdRef = useRef<string | null>(playerId);
  playerIdRef.current = playerId;

  // 맵 테마는 room_state 로만 내려온다(스냅샷에 매 틱 싣기엔 무겁다).
  // 무작위 맵이면 라운드마다 바뀌므로 서버가 그때마다 room_state 를 다시 쏜다.
  const theme = useGameStore((s: StoreSlice) => s.room?.map?.theme) as MapTheme | undefined;
  useEffect(() => {
    setMapTheme(theme);
  }, [theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    let raf = 0;
    let scale = 0;
    let lastTick = -1;
    let lastPhase: Phase | null = null;
    let lastMapId: string | null = null;

    // 백버퍼는 "표시 크기 × 픽셀비율" 로 맞춘다. 전체화면에서는 캔버스가 800px 보다
    // 훨씬 커지는데, 800×600 백버퍼를 늘려 그리면 선이 뭉개진다.
    // 표시 크기는 ResizeObserver 로만 잰다(매 프레임 clientWidth 를 읽으면 레이아웃이 강제된다).
    let cssWidth = canvas.clientWidth || WORLD_WIDTH;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) cssWidth = width;
    });
    observer.observe(canvas);

    const fitToDisplay = (): void => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const next = Math.min(Math.max((cssWidth / WORLD_WIDTH) * dpr, 1), 3);
      if (Math.abs(next - scale) < 0.02) return;
      scale = next;
      canvas.width = Math.round(WORLD_WIDTH * scale);
      canvas.height = Math.round(WORLD_HEIGHT * scale);
      // 백버퍼 크기를 바꾸면 컨텍스트 상태가 초기화된다 — 변환을 다시 건다.
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.imageSmoothingEnabled = true;
    };

    const loop = (t: number): void => {
      raf = window.requestAnimationFrame(loop);
      fitToDisplay();
      const snap = net.latest;
      if (!snap) {
        ctx.fillStyle = backgroundColor();
        ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
        return;
      }
      // 라운드 재시작 / 리스폰 / 맵 교체 시 보간 상태를 비운다.
      if (
        snap.tick < lastTick ||
        (lastPhase !== 'playing' && snap.phase === 'playing') ||
        (lastMapId !== null && lastMapId !== snap.map_id)
      ) {
        resetInterpolation();
      }
      lastTick = snap.tick;
      lastPhase = snap.phase;
      lastMapId = snap.map_id;
      renderFrame(ctx, snap, playerIdRef.current, t);
    };

    raf = window.requestAnimationFrame(loop);
    return () => {
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      resetInterpolation();
    };
  }, [canvasRef]);

  return (
    <canvas
      ref={canvasRef}
      className="game-canvas"
      width={WORLD_WIDTH}
      height={WORLD_HEIGHT}
      aria-label="Game view"
    />
  );
}

export const GameCanvas = memo(GameCanvasInner);
export default GameCanvas;
