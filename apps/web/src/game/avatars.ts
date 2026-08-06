// 캐릭터 드로잉 진입점. 파츠 테이블은 avatarParts.ts 에 있다.
import type { Customization, PartOffset, PartOffsets, PartSlot } from '@/types/game';
import {
  COLORS,
  DEFAULT_COLOR,
  DETAILS,
  DETAILS2,
  EYES,
  MOUTHS,
  type PartOption,
} from './avatarParts';

export { COLORS, DEFAULT_COLOR, DETAILS, DETAILS2, EYES, MOUTHS };
export type { ColorOption, PartOption, PartDraw } from './avatarParts';

/** 편집기 탭 = 파츠 슬롯. types/game 의 PartSlot 과 같은 값이다. */
export type PartCategory = PartSlot;

/** 카테고리 → 파츠 테이블 */
export const PART_TABLE: Record<PartCategory, PartOption[]> = {
  eye: EYES,
  mouth: MOUTHS,
  detail: DETAILS,
  detail2: DETAILS2,
};

/** 편집기 탭 순서/라벨 (사진의 EYES · MOUTHS · DETAIL1 · DETAIL2) */
export const PART_CATEGORIES: PartCategory[] = ['eye', 'mouth', 'detail', 'detail2'];

export const PART_LABEL: Record<PartCategory, string> = {
  eye: 'EYES',
  mouth: 'MOUTHS',
  detail: 'DETAIL1',
  detail2: 'DETAIL2',
};

/**
 * 슬롯별 "파츠가 대체로 차지하는 영역"(몸통 박스 대비 비율).
 * 편집기가 드래그 핸들을 어디에 띄울지 정하는 용도라 정확할 필요는 없다.
 */
export const PART_ANCHOR: Record<PartCategory, { x: number; y: number; w: number; h: number }> = {
  eye: { x: 0.5, y: 0.42, w: 0.78, h: 0.36 },
  mouth: { x: 0.5, y: 0.75, w: 0.5, h: 0.3 },
  detail: { x: 0.5, y: 0.58, w: 0.86, h: 0.56 },
  detail2: { x: 0.5, y: 0.06, w: 0.96, h: 0.44 },
};

/** 파츠를 몸통 밖으로 완전히 밀어내지 못하게 하는 한계(박스 대비 비율) */
export const MAX_OFFSET = 0.32;

export const DEFAULT_CUSTOMIZATION: Customization = {
  eye: 0,
  mouth: 0,
  detail: 0,
  detail2: 0,
  color: DEFAULT_COLOR,
  offsets: {},
};

export interface DrawAvatarOptions {
  /** 사망 상태: 회색 + 반투명 */
  dead?: boolean;
  /** 발밑 그림자 */
  shadow?: boolean;
  /** 전체 투명도(0~1) */
  alpha?: number;
  /** 몸통 테두리 색 (없으면 기본 어두운 테두리) */
  outline?: string | null;
}

function clampIndex(value: number, length: number): number {
  if (!Number.isFinite(value)) return 0;
  const i = Math.floor(value);
  return i < 0 || i >= length ? 0 : i;
}

function clampAxis(value: unknown): number {
  const n = typeof value === 'number' ? value : Number.NaN;
  if (!Number.isFinite(n)) return 0;
  return Math.max(-MAX_OFFSET, Math.min(MAX_OFFSET, n));
}

/** 저장/수신한 오프셋을 안전한 값으로 정리한다. */
export function clampOffset(raw: PartOffset | undefined | null): PartOffset {
  if (!raw) return { x: 0, y: 0 };
  return { x: clampAxis(raw.x), y: clampAxis(raw.y) };
}

export function offsetOf(c: Customization | undefined | null, slot: PartCategory): PartOffset {
  return clampOffset(c?.offsets?.[slot]);
}

/** 오프셋 하나만 바꾼 새 customization (편집기 드래그용) */
export function withOffset(c: Customization, slot: PartCategory, next: PartOffset): Customization {
  const offsets: PartOffsets = { ...(c.offsets ?? {}), [slot]: clampOffset(next) };
  return { ...c, offsets };
}

/** #rrggbb → 회색조 hex. 잘못된 값이면 중간 회색. */
function toGray(hex: string): string {
  if (typeof hex !== 'string' || hex.length !== 7 || hex[0] !== '#') return '#8b8b8b';
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  if (Number.isNaN(r) || Number.isNaN(g) || Number.isNaN(b)) return '#8b8b8b';
  const v = Math.round(r * 0.3 + g * 0.59 + b * 0.11);
  const s = v.toString(16).padStart(2, '0');
  return `#${s}${s}${s}`;
}

/** 파츠 하나를 오프셋만큼 밀어서 그린다. */
function drawPart(
  ctx: CanvasRenderingContext2D,
  part: PartOption,
  x: number,
  y: number,
  w: number,
  h: number,
  off: PartOffset,
): void {
  ctx.save();
  if (off.x !== 0 || off.y !== 0) ctx.translate(off.x * w, off.y * h);
  part.draw(ctx, x, y, w, h);
  ctx.restore();
}

/**
 * 캐릭터 1명을 (x, y, w, h) 박스에 그린다. 몸통은 박스 중앙의 원.
 * ctx 상태는 save/restore 로 복원된다.
 */
export function drawAvatar(
  ctx: CanvasRenderingContext2D,
  c: Customization | undefined | null,
  x: number,
  y: number,
  w: number,
  h: number,
  opts?: DrawAvatarOptions,
): void {
  const eye = clampIndex(c ? c.eye : 0, EYES.length);
  const mouth = clampIndex(c ? c.mouth : 0, MOUTHS.length);
  const detail = clampIndex(c ? c.detail : 0, DETAILS.length);
  const detail2 = clampIndex(c ? c.detail2 : 0, DETAILS2.length);
  const rawColor = c && typeof c.color === 'string' ? c.color : DEFAULT_COLOR;
  const dead = opts?.dead === true;
  const body = dead ? toGray(rawColor) : rawColor;

  ctx.save();
  ctx.globalAlpha = opts?.alpha ?? (dead ? 0.45 : 1);

  if (opts?.shadow) {
    ctx.save();
    ctx.globalAlpha *= 0.35;
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.ellipse(x + w / 2, y + h - 2, w * 0.35, h * 0.12, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // 몸통
  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.arc(x + w / 2, y + h / 2, w / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = opts?.outline ?? 'rgba(0,0,0,0.25)';
  ctx.stroke();

  // 얼굴 파츠 — 머리 위 액세서리(detail2)를 제일 먼저 깔아 얼굴을 가리지 않게 한다.
  drawPart(ctx, DETAILS2[detail2], x, y, w, h, offsetOf(c, 'detail2'));
  drawPart(ctx, EYES[eye], x, y, w, h, offsetOf(c, 'eye'));
  drawPart(ctx, MOUTHS[mouth], x, y, w, h, offsetOf(c, 'mouth'));
  drawPart(ctx, DETAILS[detail], x, y, w, h, offsetOf(c, 'detail'));

  ctx.restore();
}

/** 아바타 편집기 썸네일용: 몸통 원 위에 파츠 하나만 그린다. */
export function drawPartThumbnail(
  ctx: CanvasRenderingContext2D,
  part: PartOption,
  size: number,
  bodyColor = '#d5dae2',
): void {
  ctx.clearRect(0, 0, size, size);
  // 머리 위로 삐져나오는 파츠(뿔 · 왕관 …)를 담으려고 몸통을 조금 작게 그린다.
  const pad = size * 0.16;
  const box = size - pad * 2;
  ctx.fillStyle = bodyColor;
  ctx.beginPath();
  ctx.arc(size / 2, pad + box / 2, box / 2, 0, Math.PI * 2);
  ctx.fill();
  part.draw(ctx, pad, pad, box, box);
}
