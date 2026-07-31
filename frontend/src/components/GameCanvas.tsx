// 800x600 고정 해상도 캔버스. rAF 루프에서 net.latest 를 직접 읽는다(React state 사용 금지).
import { memo, useEffect, useRef } from 'react';
import type { JSX, RefObject } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { renderFrame, resetInterpolation } from '@/game/renderer';
import { WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { Phase } from '@/types/game';

interface StoreSlice {
  playerId: string | null;
}

interface GameCanvasProps {
  canvasRef: RefObject<HTMLCanvasElement | null>;
}

function GameCanvasInner({ canvasRef }: GameCanvasProps): JSX.Element {
  const playerId = useGameStore((s: StoreSlice) => s.playerId);
  const playerIdRef = useRef<string | null>(playerId);
  playerIdRef.current = playerId;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    let raf = 0;
    let dpr = 0;
    let lastTick = -1;
    let lastPhase: Phase | null = null;

    const fitToDpr = (): void => {
      const next = Math.min(window.devicePixelRatio || 1, 2);
      if (next === dpr) return;
      dpr = next;
      canvas.width = Math.round(WORLD_WIDTH * dpr);
      canvas.height = Math.round(WORLD_HEIGHT * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingEnabled = true;
    };

    const loop = (t: number): void => {
      raf = window.requestAnimationFrame(loop);
      fitToDpr();
      const snap = net.latest;
      if (!snap) {
        ctx.fillStyle = '#0b0f1a';
        ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
        return;
      }
      // 라운드 재시작/리스폰 시 보간 상태를 비운다.
      if (snap.tick < lastTick || (lastPhase !== 'playing' && snap.phase === 'playing')) {
        resetInterpolation();
      }
      lastTick = snap.tick;
      lastPhase = snap.phase;
      renderFrame(ctx, snap, playerIdRef.current, t);
    };

    raf = window.requestAnimationFrame(loop);
    return () => {
      window.cancelAnimationFrame(raf);
      resetInterpolation();
    };
  }, [canvasRef]);

  return (
    <canvas
      ref={canvasRef}
      className="game-canvas"
      width={WORLD_WIDTH}
      height={WORLD_HEIGHT}
      aria-label="게임 화면"
    />
  );
}

export const GameCanvas = memo(GameCanvasInner);
export default GameCanvas;
