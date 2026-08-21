// 로비에서 쓰는 아바타 편집기. props 시그니처는 LobbyScreen 과의 계약이므로 바꾸지 않는다.
//
// 로비에는 작은 런처(미리보기 + "꾸미기")만 놓고, 실제 편집은 전체화면 오버레이에서 한다.
// 레이아웃은 ROUNDS 캐릭터 편집기와 같은 구성이다:
//   왼쪽  — 큰 캐릭터 + 드래그 핸들("파츠 이동") + 색상 + DONE
//   오른쪽 — EYES / MOUTHS / DETAIL1 / DETAIL2 탭 + 7열 썸네일 그리드
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type { JSX, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { useGameStore } from '@/store/gameStore';
import {
  COLORS,
  MAX_OFFSET,
  MAX_PART_PRICE,
  MIN_PAID_PRICE,
  PART_ANCHOR,
  PART_CATEGORIES,
  PART_LABEL,
  PART_TABLE,
  drawAvatar,
  drawPartThumbnail,
  offsetOf,
  partPrice,
  withOffset,
} from '@/game/avatars';
import type { PartCategory } from '@/game/avatars';
import type { PartOption } from '@/game/avatarParts';
import type { Customization, PartOffset } from '@/types/game';
import { SHOP_CATEGORY, useLocalProfile } from '@/hooks/useLocalProfile';
import '@/styles/game.css';

const THUMB = 52;
/** 런처(로비 카드) 미리보기 크기 */
const MINI = 86;
/** 편집기 스테이지 한 변 */
const STAGE = 260;
/** 스테이지 여백 비율 — 머리 위로 솟는 액세서리 자리 */
const STAGE_PAD = 0.2;
/** 스테이지 안에서 캐릭터 몸통이 차지하는 픽셀 */
const BODY = STAGE * (1 - STAGE_PAD * 2);
/** 구매 안내 문구가 떠 있는 시간(ms) */
const NOTICE_MS = 2000;
/** 키보드로 파츠를 옮길 때 한 번에 움직이는 양 */
const NUDGE = 0.02;

/** detail 계열의 0번은 "없음" 이라 옮길 것이 없다. */
function hasPart(slot: PartCategory, index: number): boolean {
  return !((slot === 'detail' || slot === 'detail2') && index === 0);
}

/** 슬롯 썸네일 여백 — 머리 액세서리는 크게 준다. */
function thumbPad(slot: PartCategory): number {
  return slot === 'detail2' ? 0.2 : 0.08;
}

interface StoreSlice {
  customization: Customization;
  setCustomization: (c: Customization) => void;
}

export interface AvatarEditorProps {
  /** 생략하면 store 의 customization 을 사용한다. */
  value?: Customization;
  /** 생략하면 store 의 setCustomization 을 호출한다. */
  onChange?: (c: Customization) => void;
  /** 편집기를 처음부터 펼친 상태로 띄운다. */
  defaultOpen?: boolean;
}

interface ThumbProps {
  part: PartOption;
  slot: PartCategory;
  color: string;
  selected: boolean;
  /** 잠긴 항목이면 가격(코인). 이미 보유했거나 무료면 null */
  price: number | null;
  /** 잠겼는데 코인이 모자라는가(구매 버튼을 흐리게 표시) */
  tooPoor: boolean;
  /** 다른 구매의 응답을 기다리는 중 — 잠긴 항목만 잠시 잠근다 */
  busy: boolean;
  onSelect: () => void;
}

function PartThumb({ part, slot, color, selected, price, tooPoor, busy, onSelect }: ThumbProps): JSX.Element {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const locked = price !== null;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    drawPartThumbnail(ctx, part, THUMB, color, thumbPad(slot));
  }, [part, color, slot]);

  // 등급(tier)은 테두리/가격표 색으로 드러난다 — 뒤로 갈수록 화려하고 비싸다.
  const className =
    `ae-item t${part.tier}${selected ? ' selected' : ''}${locked ? ' locked' : ''}` +
    `${locked && tooPoor ? ' too-poor' : ''}`;

  return (
    <button
      type="button"
      className={className}
      disabled={locked && busy}
      onClick={onSelect}
      title={locked ? `${part.label} — ${price}코인` : part.label}
      aria-label={locked ? `${part.label} (${price}코인)` : part.label}
      aria-pressed={selected}
    >
      <canvas ref={ref} width={THUMB * 2} height={THUMB * 2} />
      {locked ? <span className="ae-price">🔒{price}</span> : null}
    </button>
  );
}

const Thumb = memo(PartThumb);

/** 캐릭터 위에 뜨는 드래그 핸들 — 사진의 파란 점 4개짜리 상자 */
interface HandleProps {
  slot: PartCategory;
  offset: PartOffset;
  onMove: (next: PartOffset) => void;
  onReset: () => void;
}

function DragHandle({ slot, offset, onMove, onReset }: HandleProps): JSX.Element {
  const anchor = PART_ANCHOR[slot];
  const drag = useRef<{ id: number; x: number; y: number; from: PartOffset } | null>(null);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, from: offset };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [offset],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const d = drag.current;
      if (!d || d.id !== e.pointerId) return;
      onMove({
        x: d.from.x + (e.clientX - d.x) / BODY,
        y: d.from.y + (e.clientY - d.y) / BODY,
      });
    },
    [onMove],
  );

  const endDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current?.id === e.pointerId) drag.current = null;
  }, []);

  // 방향키로도 옮길 수 있게 (마우스가 없거나 미세 조정할 때)
  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLDivElement>) => {
      const step: Record<string, [number, number]> = {
        ArrowLeft: [-NUDGE, 0],
        ArrowRight: [NUDGE, 0],
        ArrowUp: [0, -NUDGE],
        ArrowDown: [0, NUDGE],
      };
      const move = step[e.key];
      if (move) {
        e.preventDefault();
        onMove({ x: offset.x + move[0], y: offset.y + move[1] });
      } else if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault();
        onReset();
      }
    },
    [offset, onMove, onReset],
  );

  const moved = offset.x !== 0 || offset.y !== 0;
  const left = STAGE * STAGE_PAD + (anchor.x + offset.x - anchor.w / 2) * BODY;
  const top = STAGE * STAGE_PAD + (anchor.y + offset.y - anchor.h / 2) * BODY;

  return (
    <div
      className="ae-handle"
      style={{ left, top, width: anchor.w * BODY, height: anchor.h * BODY }}
      role="button"
      tabIndex={0}
      aria-label={
        `${PART_LABEL[slot]} 위치 — 드래그하거나 방향키로 옮기세요 ` +
        `(가로 ${Math.round((offset.x / MAX_OFFSET) * 100)}%, ` +
        `세로 ${Math.round((offset.y / MAX_OFFSET) * 100)}%)`
      }
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
    >
      <i className="ae-dot tl" />
      <i className="ae-dot tr" />
      <i className="ae-dot bl" />
      <i className="ae-dot br" />
      {moved ? (
        <button
          type="button"
          className="ae-handle-reset"
          title="위치 되돌리기"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onReset}
        >
          ↺
        </button>
      ) : null}
    </div>
  );
}

/** 로비 카드에 박히는 작은 미리보기 */
function MiniPreview({ value, size }: { value: Customization; size: number }): JSX.Element {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    ctx.clearRect(0, 0, size, size);
    const pad = size * STAGE_PAD;
    drawAvatar(ctx, value, pad, pad, size - pad * 2, size - pad * 2, { shadow: false });
  }, [value, size]);

  return (
    <canvas
      ref={ref}
      width={size * 2}
      height={size * 2}
      style={{ width: size, height: size }}
      aria-label="캐릭터 미리보기"
    />
  );
}

function AvatarEditorInner(props: AvatarEditorProps): JSX.Element {
  const storeValue = useGameStore((s: StoreSlice) => s.customization);
  const storeSet = useGameStore((s: StoreSlice) => s.setCustomization);
  const value = props.value ?? storeValue;
  const onChange = props.onChange ?? storeSet;

  const [open, setOpen] = useState(props.defaultOpen === true);
  const [tab, setTab] = useState<PartCategory>('eye');
  // 객체로 담는 이유: 같은 문구를 다시 띄워도 참조가 바뀌어야 2초 타이머가 다시 시작된다.
  const [notice, setNotice] = useState<{ text: string } | null>(null);
  const previewRef = useRef<HTMLCanvasElement | null>(null);
  const { coins, isOwned, buyItem, buying } = useLocalProfile();

  /** 안내 문구는 2초 뒤 저절로 사라진다. */
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  /** 편집 중에는 Esc 로 닫고, 뒤쪽 로비가 스크롤되지 않게 막는다. */
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    const canvas = previewRef.current;
    if (!open || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    ctx.clearRect(0, 0, STAGE, STAGE);
    const pad = STAGE * STAGE_PAD;
    drawAvatar(ctx, value, pad, pad, BODY, BODY, { shadow: false });
  }, [value, open]);

  /** 잠긴 파츠는 먼저 산다. 구매가 거절되면 선택하지 않고 안내만 남긴다. */
  const selectPart = useCallback(
    async (category: PartCategory, index: number) => {
      const shopKey = SHOP_CATEGORY[category] ?? category;
      if (!isOwned(shopKey, index)) {
        // 가격도 결과도 서버가 정한다. 실패 사유 문구는 훅이 만들어 준다.
        const result = await buyItem(shopKey, index);
        if (!result.ok) {
          if (result.message) setNotice({ text: result.message });
          return;
        }
        setNotice(
          result.spent > 0
            ? { text: `${PART_TABLE[category][index]?.label ?? '아이템'} 구매 완료! -${result.spent}코인` }
            : null,
        );
      } else {
        setNotice(null);
      }

      const next: Customization = { ...value };
      if (category === 'eye') next.eye = index;
      else if (category === 'mouth') next.mouth = index;
      else if (category === 'detail') next.detail = index;
      else next.detail2 = index;
      onChange(next);
    },
    [buyItem, isOwned, onChange, value],
  );

  const setColor = useCallback(
    (color: string) => {
      onChange({ ...value, color });
    },
    [onChange, value],
  );

  const moveActive = useCallback(
    (next: PartOffset) => {
      onChange(withOffset(value, tab, next));
    },
    [onChange, tab, value],
  );

  const resetActive = useCallback(() => {
    onChange(withOffset(value, tab, { x: 0, y: 0 }));
  }, [onChange, tab, value]);

  const parts = PART_TABLE[tab];
  const activeIndex = value[tab] ?? 0;

  if (!open) {
    return (
      <div className="ae-launcher">
        <MiniPreview value={value} size={MINI} />
        <div className="ae-launcher-text">
          <b>내 캐릭터</b>
          <span>눈 · 입 · 디테일 · 액세서리를 고르고 파츠 위치까지 옮길 수 있어요.</span>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>
          꾸미기
        </button>
      </div>
    );
  }

  return (
    <div className="ae-modal" role="dialog" aria-modal="true" aria-label="캐릭터 꾸미기">
      <div className="ae-modal-body">
        {/* ── 왼쪽: 캐릭터 스테이지 ─────────────────────────── */}
        <div className="ae-stage-col">
          <div className="ae-move-hint" aria-hidden>
            <span className="ae-move-icon">🖱</span>
            <span className="ae-move-arrow">↕</span>
            <span className="ae-move-text">
              드래그해서
              <br />
              파츠 이동
            </span>
          </div>

          <div className="ae-stage" style={{ width: STAGE, height: STAGE }}>
            <canvas
              ref={previewRef}
              width={STAGE * 2}
              height={STAGE * 2}
              style={{ width: STAGE, height: STAGE }}
              aria-label="캐릭터 미리보기"
            />
            {hasPart(tab, activeIndex) ? (
              <DragHandle
                slot={tab}
                offset={offsetOf(value, tab)}
                onMove={moveActive}
                onReset={resetActive}
              />
            ) : null}
          </div>

          <div className="ae-colors" role="group" aria-label="몸통 색상">
            {COLORS.map((c) => (
              <button
                type="button"
                key={c.val}
                className={`ae-color${value.color === c.val ? ' selected' : ''}`}
                style={{ background: c.val }}
                title={c.label}
                aria-label={c.label}
                aria-pressed={value.color === c.val}
                onClick={() => setColor(c.val)}
              />
            ))}
          </div>

          <button type="button" className="ae-done" onClick={() => setOpen(false)}>
            DONE
          </button>
        </div>

        {/* ── 오른쪽: 탭 + 파츠 그리드 ──────────────────────── */}
        <div className="ae-picker">
          <div className="ae-tabs" role="tablist" aria-label="파츠 종류">
            {PART_CATEGORIES.map((key) => (
              <button
                type="button"
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={`ae-tab${tab === key ? ' active' : ''}`}
                onClick={() => {
                  setTab(key);
                  setNotice(null); // 안내는 파츠 목록에 딸린 문구다. 탭을 옮기면 지운다.
                }}
              >
                {PART_LABEL[key]}
              </button>
            ))}
          </div>

          <div className="ae-grid">
            {parts.map((part, i) => {
              const shopKey = SHOP_CATEGORY[tab] ?? tab;
              const owned = isOwned(shopKey, i);
              const price = partPrice(tab, i);
              return (
                <Thumb
                  key={part.name}
                  part={part}
                  slot={tab}
                  color={value.color}
                  selected={activeIndex === i}
                  price={owned ? null : price}
                  tooPoor={!owned && coins < price}
                  busy={buying}
                  onSelect={() => void selectPart(tab, i)}
                />
              );
            })}
          </div>

          <div className="ae-foot">
            <span className="ae-shop-hint">
              🔒 Fancier parts cost more — <b>{MIN_PAID_PRICE}–{MAX_PART_PRICE} coins</b> · you have
              💰 {coins}
            </span>
            {notice ? <span className="ae-notice">{notice.text}</span> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export const AvatarEditor = memo(AvatarEditorInner);
export default AvatarEditor;
