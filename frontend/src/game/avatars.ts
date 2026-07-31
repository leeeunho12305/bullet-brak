// 캐릭터 드로잉 진입점. 파츠 테이블은 avatarParts.ts 에 있다.
import type { Customization } from '@/types/game';
import {
  COLORS,
  DEFAULT_COLOR,
  DETAILS,
  EYES,
  MOUTHS,
  type PartOption,
} from './avatarParts';

export { COLORS, DEFAULT_COLOR, DETAILS, EYES, MOUTHS };
export type { ColorOption, PartOption, PartDraw } from './avatarParts';

export type PartCategory = 'eye' | 'mouth' | 'detail';

/** 카테고리 → 파츠 테이블 */
export const PART_TABLE: Record<PartCategory, PartOption[]> = {
  eye: EYES,
  mouth: MOUTHS,
  detail: DETAILS,
};

export const DEFAULT_CUSTOMIZATION: Customization = {
  eye: 0,
  mouth: 0,
  detail: 0,
  color: DEFAULT_COLOR,
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

  // 얼굴 파츠
  EYES[eye].draw(ctx, x, y, w, h);
  MOUTHS[mouth].draw(ctx, x, y, w, h);
  DETAILS[detail].draw(ctx, x, y, w, h);

  ctx.restore();
}

/** 아바타 편집기 썸네일용: 회색 원 위에 파츠 하나만 그린다. */
export function drawPartThumbnail(
  ctx: CanvasRenderingContext2D,
  part: PartOption,
  size: number,
  bodyColor = '#d5dae2',
): void {
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = bodyColor;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 1, 0, Math.PI * 2);
  ctx.fill();
  part.draw(ctx, 0, 0, size, size);
}
