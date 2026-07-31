// 키보드/마우스 입력 → 서버 메시지. 입력이 "바뀔 때만" 전송한다.
import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';
import { net } from '@/net/connection';
import { WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { InputState, Snapshot } from '@/types/game';
import { spawnMuzzleFlash } from './renderer';

/** 조준 전송 주기 (30Hz) */
const AIM_INTERVAL = 34;
/** 좌클릭을 이 시간 이상 누르면 강공격 차징으로 전환 */
const STRONG_HOLD_MS = 350;

export interface UseInputOptions {
  /** false 면 모든 입력을 무시한다(로비/결과 화면 등) */
  enabled?: boolean;
  /** 내 플레이어 id — 총구 화염 위치 계산용 */
  myId?: string | null;
}

/** 채팅 입력 중이면 게임 입력을 먹지 않는다. */
function isTyping(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  return el instanceof HTMLElement && el.isContentEditable;
}

export function useInput(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  options?: UseInputOptions,
): void {
  const optionsRef = useRef<UseInputOptions>(options ?? {});
  optionsRef.current = options ?? {};

  useEffect(() => {
    const input: InputState = { left: false, right: false, jump: false, block: false };
    const sent: InputState = { left: false, right: false, jump: false, block: false };
    let mouseBlock = false;
    let keyBlock = false;
    let strongActive = false;
    let holdTimer: number | null = null;
    let aimX = WORLD_WIDTH / 2;
    let aimY = WORLD_HEIGHT / 2;
    let aimDirty = false;
    let lastAimSent = 0;

    const isEnabled = (): boolean => optionsRef.current.enabled !== false;

    const send = (msg: Parameters<typeof net.send>[0]): void => {
      if (net.isOpen()) net.send(msg);
    };

    const flushInput = (): void => {
      input.block = mouseBlock || keyBlock;
      if (
        input.left === sent.left &&
        input.right === sent.right &&
        input.jump === sent.jump &&
        input.block === sent.block
      ) {
        return;
      }
      sent.left = input.left;
      sent.right = input.right;
      sent.jump = input.jump;
      sent.block = input.block;
      send({ type: 'input', left: input.left, right: input.right, jump: input.jump, block: input.block });
    };

    const flushAim = (now: number): void => {
      if (!aimDirty || now - lastAimSent < AIM_INTERVAL) return;
      aimDirty = false;
      lastAimSent = now;
      send({ type: 'aim', x: aimX, y: aimY });
    };

    const clearAll = (): void => {
      input.left = false;
      input.right = false;
      input.jump = false;
      mouseBlock = false;
      keyBlock = false;
      if (holdTimer !== null) {
        window.clearTimeout(holdTimer);
        holdTimer = null;
      }
      if (strongActive) {
        strongActive = false;
        send({ type: 'strong_release' });
      }
      flushInput();
    };

    const startStrong = (): void => {
      if (strongActive) return;
      strongActive = true;
      send({ type: 'strong_start' });
    };

    const releaseStrong = (): void => {
      if (!strongActive) return;
      strongActive = false;
      send({ type: 'strong_release' });
    };

    const onKeyDown = (e: KeyboardEvent): void => {
      if (!isEnabled() || isTyping()) return;
      switch (e.code) {
        case 'KeyA':
        case 'ArrowLeft':
          input.left = true;
          break;
        case 'KeyD':
        case 'ArrowRight':
          input.right = true;
          break;
        case 'Space':
        case 'KeyW':
        case 'ArrowUp':
          e.preventDefault();
          input.jump = true;
          break;
        case 'ShiftLeft':
        case 'ShiftRight':
        case 'KeyS':
          keyBlock = true;
          break;
        case 'KeyE':
        case 'KeyX':
          if (!e.repeat) {
            e.preventDefault();
            startStrong();
          }
          return;
        default:
          return;
      }
      flushInput();
    };

    const onKeyUp = (e: KeyboardEvent): void => {
      if (!isEnabled()) return;
      switch (e.code) {
        case 'KeyA':
        case 'ArrowLeft':
          input.left = false;
          break;
        case 'KeyD':
        case 'ArrowRight':
          input.right = false;
          break;
        case 'Space':
        case 'KeyW':
        case 'ArrowUp':
          input.jump = false;
          break;
        case 'ShiftLeft':
        case 'ShiftRight':
        case 'KeyS':
          keyBlock = false;
          break;
        case 'KeyE':
        case 'KeyX':
          releaseStrong();
          return;
        default:
          return;
      }
      flushInput();
    };

    const updateAim = (e: MouseEvent): void => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      aimX = ((e.clientX - rect.left) / rect.width) * WORLD_WIDTH;
      aimY = ((e.clientY - rect.top) / rect.height) * WORLD_HEIGHT;
      aimDirty = true;
    };

    const onMouseMove = (e: MouseEvent): void => {
      if (!isEnabled()) return;
      updateAim(e);
      flushAim(performance.now());
    };

    const shoot = (): void => {
      // 조준값을 먼저 확정한 뒤 발사한다.
      if (aimDirty) {
        aimDirty = false;
        lastAimSent = performance.now();
        send({ type: 'aim', x: aimX, y: aimY });
      }
      send({ type: 'shoot' });

      const snap: Snapshot | null = net.latest;
      const myId = optionsRef.current.myId ?? null;
      if (!snap || !myId) return;
      for (let i = 0; i < snap.players.length; i += 1) {
        const p = snap.players[i];
        if (p.id !== myId || !p.alive) continue;
        const cx = p.x + p.width / 2;
        const cy = p.y + p.height / 2;
        const angle = Math.atan2(aimY - cy, aimX - cx);
        spawnMuzzleFlash(cx + Math.cos(angle) * 26, cy + Math.sin(angle) * 26, angle, performance.now());
        break;
      }
    };

    const onMouseDown = (e: MouseEvent): void => {
      if (!isEnabled() || isTyping()) return;
      const canvas = canvasRef.current;
      if (canvas && e.target instanceof Node && !canvas.contains(e.target) && e.target !== canvas) {
        // 캔버스 밖(버튼/채팅 등) 클릭은 게임 입력으로 처리하지 않는다.
        return;
      }
      updateAim(e);
      if (e.button === 0) {
        e.preventDefault();
        shoot();
        holdTimer = window.setTimeout(() => {
          holdTimer = null;
          startStrong();
        }, STRONG_HOLD_MS);
      } else if (e.button === 2) {
        e.preventDefault();
        mouseBlock = true;
        flushInput();
      }
    };

    const onMouseUp = (e: MouseEvent): void => {
      if (e.button === 0) {
        if (holdTimer !== null) {
          window.clearTimeout(holdTimer);
          holdTimer = null;
        }
        releaseStrong();
      } else if (e.button === 2) {
        mouseBlock = false;
        flushInput();
      }
    };

    const onContextMenu = (e: MouseEvent): void => {
      e.preventDefault();
    };

    const onBlur = (): void => clearAll();

    // 스로틀 보정: 마우스가 멈춰도 마지막 조준값은 반드시 한 번 전송된다.
    const aimTimer = window.setInterval(() => {
      if (isEnabled()) flushAim(performance.now());
    }, AIM_INTERVAL);

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('contextmenu', onContextMenu);
    window.addEventListener('blur', onBlur);

    return () => {
      window.clearInterval(aimTimer);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('blur', onBlur);
      clearAll();
    };
  }, [canvasRef]);
}
