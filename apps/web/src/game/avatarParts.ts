// 캐릭터 파츠 카탈로그. 레거시 client/src/app.js 의 options 배열에서 출발했고,
// ROUNDS 스타일 편집기(EYES / MOUTHS / DETAIL1 / DETAIL2)를 채우려고 대폭 늘렸다.
//
// 규칙 두 가지만 지키면 얼마든지 더 추가해도 된다.
//  1) 모든 draw 는 (x, y, w, h) 사각형 안에 비율로만 그린다 → 크기와 무관하게 같은 그림.
//  2) 기존 항목의 "순서"는 절대 바꾸지 않는다. 저장된 customization 이 index 로 참조한다.
//     새 파츠는 항상 배열 뒤에 붙인다.

export type PartDraw = (
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) => void;

export interface PartOption {
  /** 내부 식별용 이름 (React key 로도 쓰므로 배열 안에서 고유해야 한다) */
  name: string;
  /** UI 표기용 한국어 라벨 */
  label: string;
  draw: PartDraw;
}

export interface ColorOption {
  name: string;
  label: string;
  val: string;
}

// --------------------------------------------------------------------------
// 드로잉 헬퍼
// --------------------------------------------------------------------------

const INK = '#111318';
const WHITE = '#fff';

/** 선 두께: 인게임(약 30px)에서는 2px, 편집기 프리뷰(150px)에서는 굵게 */
function lw(u: number): number {
  return Math.max(2, u * 0.045);
}

function disc(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, color = INK): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
}

function ring(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  width: number,
  color = INK,
): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
}

function poly(ctx: CanvasRenderingContext2D, pts: number[][], color = INK): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
  ctx.closePath();
  ctx.fill();
}

function path(
  ctx: CanvasRenderingContext2D,
  pts: number[][],
  width: number,
  color = INK,
  close = false,
): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
  if (close) ctx.closePath();
  ctx.stroke();
}

function curve(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  a0: number,
  a1: number,
  width: number,
  color = INK,
): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(cx, cy, r, a0, a1);
  ctx.stroke();
}

function ellipse(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  color = INK,
  rot = 0,
): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, rot, 0, Math.PI * 2);
  ctx.fill();
}

/** 꼭짓점 n 개짜리 별 (스파클 눈 · 반짝임 디테일) */
function star(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  color = INK,
  points = 5,
): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  for (let i = 0; i < points * 2; i += 1) {
    const rad = i % 2 === 0 ? r : r * 0.42;
    const a = (Math.PI * i) / points - Math.PI / 2;
    const px = cx + Math.cos(a) * rad;
    const py = cy + Math.sin(a) * rad;
    if (i) ctx.lineTo(px, py);
    else ctx.moveTo(px, py);
  }
  ctx.closePath();
  ctx.fill();
}

function heart(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  color = INK,
): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(cx, cy + r * 0.9);
  ctx.bezierCurveTo(cx - r * 1.6, cy - r * 0.2, cx - r * 0.5, cy - r * 1.3, cx, cy - r * 0.35);
  ctx.bezierCurveTo(cx + r * 0.5, cy - r * 1.3, cx + r * 1.6, cy - r * 0.2, cx, cy + r * 0.9);
  ctx.fill();
}

/** 물방울(눈물 · 땀). 뾰족한 쪽이 위. */
function drop(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, color: string): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(cx, cy - r * 1.6);
  ctx.quadraticCurveTo(cx + r, cy, cx, cy + r);
  ctx.quadraticCurveTo(cx - r, cy, cx, cy - r * 1.6);
  ctx.fill();
}

// --------------------------------------------------------------------------
// 눈: "눈알 모양 × 눈썹" 조합으로 카탈로그를 만든다
// --------------------------------------------------------------------------

/** 눈 하나를 (cx, cy) 에 그린다. side 는 -1(왼쪽) / 1(오른쪽). u = 몸통 폭. */
type EyeDraw = (
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  u: number,
  side: -1 | 1,
) => void;

interface EyeShape {
  name: string;
  label: string;
  draw: EyeDraw;
}

const EYE_SHAPES: EyeShape[] = [
  {
    name: 'Round',
    label: '동글',
    draw: (ctx, cx, cy, u) => disc(ctx, cx, cy, u * 0.085),
  },
  {
    name: 'Big',
    label: '큰눈',
    draw: (ctx, cx, cy, u) => {
      disc(ctx, cx, cy, u * 0.13, WHITE);
      ring(ctx, cx, cy, u * 0.13, lw(u) * 0.6);
      disc(ctx, cx, cy + u * 0.02, u * 0.07);
      disc(ctx, cx - u * 0.04, cy - u * 0.04, u * 0.025, WHITE);
    },
  },
  {
    name: 'Wide',
    label: '왕눈',
    draw: (ctx, cx, cy, u, side) => {
      ellipse(ctx, cx, cy, u * 0.11, u * 0.145, WHITE);
      ring(ctx, cx, cy, u * 0.11, lw(u) * 0.5);
      disc(ctx, cx + side * u * 0.02, cy + u * 0.03, u * 0.055);
    },
  },
  {
    name: 'Sleepy',
    label: '졸림',
    draw: (ctx, cx, cy, u) => {
      curve(ctx, cx, cy, u * 0.1, Math.PI, Math.PI * 2, lw(u));
      path(ctx, [[cx - u * 0.1, cy], [cx + u * 0.1, cy]], lw(u) * 0.8);
    },
  },
  {
    name: 'Wink',
    label: '윙크',
    draw: (ctx, cx, cy, u, side) => {
      if (side < 0) {
        curve(ctx, cx, cy + u * 0.05, u * 0.1, Math.PI * 1.15, Math.PI * 1.85, lw(u));
      } else {
        disc(ctx, cx, cy, u * 0.095);
      }
    },
  },
  {
    name: 'Sparkle',
    label: '반짝',
    draw: (ctx, cx, cy, u) => {
      star(ctx, cx, cy, u * 0.135, '#ffd43b');
      star(ctx, cx, cy, u * 0.075, WHITE, 4);
    },
  },
  {
    name: 'Heart',
    label: '하트',
    draw: (ctx, cx, cy, u) => heart(ctx, cx, cy, u * 0.1, '#ff4a7d'),
  },
  {
    name: 'Dizzy',
    label: '뱅글',
    draw: (ctx, cx, cy, u) => {
      ctx.strokeStyle = INK;
      ctx.lineWidth = lw(u) * 0.75;
      ctx.beginPath();
      for (let i = 0; i <= 26; i += 1) {
        const a = (i / 26) * Math.PI * 3.2;
        const r = u * 0.012 + (i / 26) * u * 0.1;
        const px = cx + Math.cos(a) * r;
        const py = cy + Math.sin(a) * r;
        if (i) ctx.lineTo(px, py);
        else ctx.moveTo(px, py);
      }
      ctx.stroke();
    },
  },
  {
    name: 'Glasses',
    label: '안경',
    draw: (ctx, cx, cy, u, side) => {
      disc(ctx, cx, cy, u * 0.07);
      ring(ctx, cx, cy, u * 0.125, lw(u) * 0.7, '#2b2f3d');
      // 다리와 콧대는 한 번만 (오른쪽 눈을 그릴 때)
      if (side > 0) {
        const half = u * 0.18;
        path(ctx, [[cx - u * 0.125, cy], [cx - half * 1.05, cy]], lw(u) * 0.7, '#2b2f3d');
        path(ctx, [[cx + u * 0.125, cy], [cx + u * 0.2, cy - u * 0.03]], lw(u) * 0.7, '#2b2f3d');
      }
    },
  },
  {
    name: 'Monocle',
    label: '외알안경',
    draw: (ctx, cx, cy, u, side) => {
      disc(ctx, cx, cy, u * 0.075);
      if (side > 0) {
        ring(ctx, cx, cy, u * 0.14, lw(u) * 0.7, '#ffd43b');
        path(ctx, [[cx + u * 0.1, cy + u * 0.11], [cx + u * 0.15, cy + u * 0.24]], lw(u) * 0.5, '#ffd43b');
      }
    },
  },
  {
    name: 'Oval',
    label: '세로눈',
    draw: (ctx, cx, cy, u) => ellipse(ctx, cx, cy, u * 0.055, u * 0.12),
  },
  {
    name: 'Glossy',
    label: '촉촉',
    draw: (ctx, cx, cy, u) => {
      disc(ctx, cx, cy, u * 0.115);
      disc(ctx, cx - u * 0.04, cy - u * 0.045, u * 0.04, WHITE);
      disc(ctx, cx + u * 0.045, cy + u * 0.045, u * 0.02, WHITE);
    },
  },
  {
    name: 'Tired',
    label: '다크서클',
    draw: (ctx, cx, cy, u) => {
      disc(ctx, cx, cy, u * 0.07);
      curve(ctx, cx, cy + u * 0.02, u * 0.1, Math.PI * 0.15, Math.PI * 0.85, lw(u) * 0.6, '#5b6072');
      curve(ctx, cx, cy + u * 0.05, u * 0.11, Math.PI * 0.2, Math.PI * 0.8, lw(u) * 0.5, '#5b6072');
    },
  },
  {
    name: 'Slit',
    label: '실눈',
    draw: (ctx, cx, cy, u, side) => {
      path(
        ctx,
        [
          [cx - side * u * 0.1, cy - u * 0.02],
          [cx + side * u * 0.1, cy + u * 0.02],
        ],
        lw(u),
      );
    },
  },
];

interface Brow {
  name: string;
  label: string;
  /** null 이면 눈썹 없음 */
  draw: EyeDraw | null;
}

const BROWS: Brow[] = [
  { name: '', label: '', draw: null },
  {
    name: 'Angry',
    label: ' · 화남',
    draw: (ctx, cx, cy, u, side) => {
      path(
        ctx,
        [
          [cx - side * u * 0.11, cy - u * 0.05],
          [cx + side * u * 0.09, cy + u * 0.03],
        ],
        lw(u),
      );
    },
  },
  {
    name: 'Sad',
    label: ' · 슬픔',
    draw: (ctx, cx, cy, u, side) => {
      path(
        ctx,
        [
          [cx - side * u * 0.11, cy + u * 0.04],
          [cx + side * u * 0.09, cy - u * 0.04],
        ],
        lw(u),
      );
    },
  },
];

/** 눈알 모양 + 눈썹 → 좌우 한 쌍을 그리는 PartDraw */
function eyePair(shape: EyeShape, brow: Brow): PartDraw {
  return (ctx, x, y, w, h) => {
    const ey = y + h * 0.45;
    const by = y + h * 0.28;
    shape.draw(ctx, x + w * 0.32, ey, w, -1);
    shape.draw(ctx, x + w * 0.68, ey, w, 1);
    if (brow.draw) {
      brow.draw(ctx, x + w * 0.32, by, w, -1);
      brow.draw(ctx, x + w * 0.68, by, w, 1);
    }
  };
}

/** 레거시 5종 — 인덱스 0~4 는 저장된 값과의 계약이라 순서를 고정한다. */
const LEGACY_EYES: PartOption[] = [
  {
    name: 'Normal',
    label: '기본',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.3, y + h * 0.45, w * 0.08);
      disc(ctx, x + w * 0.7, y + h * 0.45, w * 0.08);
    },
  },
  {
    name: 'Angry',
    label: '분노',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.2, y + h * 0.35], [x + w * 0.4, y + h * 0.45]], lw(w));
      path(ctx, [[x + w * 0.8, y + h * 0.35], [x + w * 0.6, y + h * 0.45]], lw(w));
      disc(ctx, x + w * 0.3, y + h * 0.5, w * 0.06);
      disc(ctx, x + w * 0.7, y + h * 0.5, w * 0.06);
    },
  },
  {
    name: 'Cute',
    label: '귀염',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.3, y + h * 0.45, w * 0.1);
      disc(ctx, x + w * 0.7, y + h * 0.45, w * 0.1);
      disc(ctx, x + w * 0.28, y + h * 0.43, w * 0.03, WHITE);
      disc(ctx, x + w * 0.68, y + h * 0.43, w * 0.03, WHITE);
    },
  },
  {
    name: 'Dead',
    label: 'X눈',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.2, y + h * 0.4], [x + w * 0.4, y + h * 0.5]], lw(w));
      path(ctx, [[x + w * 0.4, y + h * 0.4], [x + w * 0.2, y + h * 0.5]], lw(w));
      path(ctx, [[x + w * 0.6, y + h * 0.4], [x + w * 0.8, y + h * 0.5]], lw(w));
      path(ctx, [[x + w * 0.8, y + h * 0.4], [x + w * 0.6, y + h * 0.5]], lw(w));
    },
  },
  {
    name: 'Cool',
    label: '선글',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = INK;
      ctx.fillRect(x + w * 0.15, y + h * 0.4, w * 0.7, h * 0.1);
    },
  },
];

/** 조합으로 만들지 않는 특수 눈 */
const SPECIAL_EYES: PartOption[] = [
  {
    name: 'Cyclops',
    label: '외눈',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.5, y + h * 0.44, w * 0.19, WHITE);
      ring(ctx, x + w * 0.5, y + h * 0.44, w * 0.19, lw(w) * 0.6);
      disc(ctx, x + w * 0.5, y + h * 0.45, w * 0.09);
      disc(ctx, x + w * 0.44, y + h * 0.38, w * 0.035, WHITE);
    },
  },
  {
    name: 'ThirdEye',
    label: '세눈',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.3, y + h * 0.48, w * 0.075);
      disc(ctx, x + w * 0.7, y + h * 0.48, w * 0.075);
      ellipse(ctx, x + w * 0.5, y + h * 0.27, w * 0.09, w * 0.06, WHITE);
      disc(ctx, x + w * 0.5, y + h * 0.27, w * 0.045);
    },
  },
];

/** 눈 카탈로그: 레거시 5 + 특수 2 + (모양 14 × 눈썹 3) */
export const EYES: PartOption[] = [
  ...LEGACY_EYES,
  ...SPECIAL_EYES,
  ...BROWS.flatMap((brow) =>
    EYE_SHAPES.map((shape) => ({
      name: `${shape.name}${brow.name}`,
      label: `${shape.label}${brow.label}`,
      draw: eyePair(shape, brow),
    })),
  ),
];

// --------------------------------------------------------------------------
// 입
// --------------------------------------------------------------------------

export const MOUTHS: PartOption[] = [
  {
    name: 'Smile',
    label: '미소',
    draw: (ctx, x, y, w, h) =>
      curve(ctx, x + w * 0.5, y + h * 0.6, w * 0.2, 0.1 * Math.PI, 0.9 * Math.PI, lw(w)),
  },
  {
    name: 'Flat',
    label: '무표정',
    draw: (ctx, x, y, w, h) =>
      path(ctx, [[x + w * 0.35, y + h * 0.75], [x + w * 0.65, y + h * 0.75]], lw(w)),
  },
  {
    name: 'O',
    label: '동그라미',
    draw: (ctx, x, y, w, h) => ring(ctx, x + w * 0.5, y + h * 0.75, w * 0.08, lw(w)),
  },
  {
    name: 'Cat',
    label: '고양이',
    draw: (ctx, x, y, w, h) => {
      curve(ctx, x + w * 0.4, y + h * 0.7, w * 0.1, 0, Math.PI, lw(w));
      curve(ctx, x + w * 0.6, y + h * 0.7, w * 0.1, 0, Math.PI, lw(w));
    },
  },
  {
    name: 'Grin',
    label: '이빨',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = WHITE;
      ctx.strokeStyle = INK;
      ctx.lineWidth = lw(w) * 0.5;
      ctx.beginPath();
      ctx.rect(x + w * 0.35, y + h * 0.7, w * 0.3, h * 0.12);
      ctx.fill();
      ctx.stroke();
      path(ctx, [[x + w * 0.35, y + h * 0.76], [x + w * 0.65, y + h * 0.76]], lw(w) * 0.5);
    },
  },
  {
    name: 'Frown',
    label: '시무룩',
    draw: (ctx, x, y, w, h) =>
      curve(ctx, x + w * 0.5, y + h * 0.85, w * 0.18, 1.15 * Math.PI, 1.85 * Math.PI, lw(w)),
  },
  {
    name: 'BigSmile',
    label: '활짝',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = INK;
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.66, w * 0.22, 0.08 * Math.PI, 0.92 * Math.PI);
      ctx.closePath();
      ctx.fill();
      ctx.save();
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.66, w * 0.22, 0.08 * Math.PI, 0.92 * Math.PI);
      ctx.clip();
      disc(ctx, x + w * 0.5, y + h * 0.9, w * 0.11, '#ff6b8b');
      ctx.restore();
    },
  },
  {
    name: 'Shout',
    label: '외침',
    draw: (ctx, x, y, w, h) => {
      ellipse(ctx, x + w * 0.5, y + h * 0.74, w * 0.13, h * 0.17);
      ellipse(ctx, x + w * 0.5, y + h * 0.84, w * 0.08, h * 0.06, '#ff6b8b');
    },
  },
  {
    name: 'Wavy',
    label: '삐죽',
    draw: (ctx, x, y, w, h) => {
      const yy = y + h * 0.74;
      path(
        ctx,
        [
          [x + w * 0.33, yy],
          [x + w * 0.42, yy - h * 0.04],
          [x + w * 0.5, yy],
          [x + w * 0.58, yy - h * 0.04],
          [x + w * 0.67, yy],
        ],
        lw(w),
      );
    },
  },
  {
    name: 'Tongue',
    label: '메롱',
    draw: (ctx, x, y, w, h) => {
      curve(ctx, x + w * 0.5, y + h * 0.62, w * 0.18, 0.12 * Math.PI, 0.88 * Math.PI, lw(w));
      ellipse(ctx, x + w * 0.56, y + h * 0.85, w * 0.07, h * 0.07, '#ff6b8b');
    },
  },
  {
    name: 'Fang',
    label: '덧니',
    draw: (ctx, x, y, w, h) => {
      curve(ctx, x + w * 0.5, y + h * 0.63, w * 0.18, 0.1 * Math.PI, 0.9 * Math.PI, lw(w));
      poly(
        ctx,
        [
          [x + w * 0.38, y + h * 0.75],
          [x + w * 0.45, y + h * 0.75],
          [x + w * 0.415, y + h * 0.86],
        ],
        WHITE,
      );
    },
  },
  {
    name: 'Vampire',
    label: '송곳니',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = INK;
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.68, w * 0.19, 0.05 * Math.PI, 0.95 * Math.PI);
      ctx.closePath();
      ctx.fill();
      poly(
        ctx,
        [
          [x + w * 0.37, y + h * 0.75],
          [x + w * 0.44, y + h * 0.75],
          [x + w * 0.405, y + h * 0.87],
        ],
        WHITE,
      );
      poly(
        ctx,
        [
          [x + w * 0.56, y + h * 0.75],
          [x + w * 0.63, y + h * 0.75],
          [x + w * 0.595, y + h * 0.87],
        ],
        WHITE,
      );
    },
  },
  {
    name: 'Smirk',
    label: '썩소',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = INK;
      ctx.lineWidth = lw(w);
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.34, y + h * 0.76);
      ctx.quadraticCurveTo(x + w * 0.52, y + h * 0.84, x + w * 0.66, y + h * 0.68);
      ctx.stroke();
    },
  },
  {
    name: 'Gasp',
    label: '헉',
    draw: (ctx, x, y, w, h) => ellipse(ctx, x + w * 0.5, y + h * 0.76, w * 0.06, h * 0.08),
  },
  {
    name: 'Teeth',
    label: '이빨악물기',
    draw: (ctx, x, y, w, h) => {
      const bx = x + w * 0.32;
      const by = y + h * 0.68;
      const bw = w * 0.36;
      const bh = h * 0.14;
      ctx.fillStyle = WHITE;
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = INK;
      ctx.lineWidth = lw(w) * 0.5;
      ctx.strokeRect(bx, by, bw, bh);
      for (let i = 1; i < 4; i += 1) {
        path(ctx, [[bx + (bw / 4) * i, by], [bx + (bw / 4) * i, by + bh]], lw(w) * 0.4);
      }
      path(ctx, [[bx, by + bh / 2], [bx + bw, by + bh / 2]], lw(w) * 0.5);
    },
  },
  {
    name: 'Lips',
    label: '입술',
    draw: (ctx, x, y, w, h) => {
      const cx = x + w * 0.5;
      const cy = y + h * 0.76;
      ctx.fillStyle = '#ff5c8a';
      ctx.beginPath();
      ctx.moveTo(cx - w * 0.12, cy);
      ctx.quadraticCurveTo(cx - w * 0.06, cy - h * 0.07, cx, cy - h * 0.015);
      ctx.quadraticCurveTo(cx + w * 0.06, cy - h * 0.07, cx + w * 0.12, cy);
      ctx.quadraticCurveTo(cx, cy + h * 0.1, cx - w * 0.12, cy);
      ctx.fill();
    },
  },
  {
    name: 'Tiny',
    label: '점입',
    draw: (ctx, x, y, w, h) => disc(ctx, x + w * 0.5, y + h * 0.76, w * 0.035),
  },
  {
    name: 'Beak',
    label: '부리',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.4, y + h * 0.68],
          [x + w * 0.6, y + h * 0.68],
          [x + w * 0.5, y + h * 0.84],
        ],
        '#ffa94d',
      );
      path(ctx, [[x + w * 0.4, y + h * 0.68], [x + w * 0.6, y + h * 0.68]], lw(w) * 0.5, '#b36c22');
    },
  },
  {
    name: 'Zigzag',
    label: '지그재그',
    draw: (ctx, x, y, w, h) => {
      const yy = y + h * 0.75;
      path(
        ctx,
        [
          [x + w * 0.32, yy],
          [x + w * 0.4, yy - h * 0.06],
          [x + w * 0.48, yy],
          [x + w * 0.56, yy - h * 0.06],
          [x + w * 0.64, yy],
          [x + w * 0.68, yy - h * 0.03],
        ],
        lw(w) * 0.8,
      );
    },
  },
  {
    name: 'Stitch',
    label: '꿰맨입',
    draw: (ctx, x, y, w, h) => {
      const yy = y + h * 0.76;
      path(ctx, [[x + w * 0.3, yy], [x + w * 0.7, yy]], lw(w) * 0.7);
      for (let i = 0; i < 4; i += 1) {
        const px = x + w * (0.36 + i * 0.09);
        path(ctx, [[px, yy - h * 0.045], [px, yy + h * 0.045]], lw(w) * 0.5);
      }
    },
  },
  {
    name: 'Drool',
    label: '침',
    draw: (ctx, x, y, w, h) => {
      curve(ctx, x + w * 0.5, y + h * 0.63, w * 0.17, 0.12 * Math.PI, 0.88 * Math.PI, lw(w));
      drop(ctx, x + w * 0.63, y + h * 0.86, w * 0.035, '#7fd7ff');
    },
  },
  {
    name: 'Whistle',
    label: '휘파람',
    draw: (ctx, x, y, w, h) => {
      ring(ctx, x + w * 0.42, y + h * 0.76, w * 0.055, lw(w) * 0.8);
      path(ctx, [[x + w * 0.55, y + h * 0.72], [x + w * 0.66, y + h * 0.68]], lw(w) * 0.5, '#8b93b8');
      path(ctx, [[x + w * 0.55, y + h * 0.79], [x + w * 0.68, y + h * 0.78]], lw(w) * 0.5, '#8b93b8');
    },
  },
  {
    name: 'Tight',
    label: '앙다문',
    draw: (ctx, x, y, w, h) => {
      const yy = y + h * 0.76;
      path(
        ctx,
        [
          [x + w * 0.33, yy - h * 0.03],
          [x + w * 0.37, yy],
          [x + w * 0.63, yy],
          [x + w * 0.67, yy - h * 0.03],
        ],
        lw(w),
      );
    },
  },
  {
    name: 'OpenWide',
    label: '입쩍',
    draw: (ctx, x, y, w, h) => {
      ellipse(ctx, x + w * 0.5, y + h * 0.75, w * 0.16, h * 0.13);
      ellipse(ctx, x + w * 0.5, y + h * 0.83, w * 0.1, h * 0.05, '#ff6b8b');
    },
  },
  {
    name: 'Kiss',
    label: '뽀뽀',
    draw: (ctx, x, y, w, h) => {
      ring(ctx, x + w * 0.5, y + h * 0.77, w * 0.05, lw(w) * 0.9, '#ff5c8a');
      heart(ctx, x + w * 0.68, y + h * 0.66, w * 0.05, 'rgba(255, 92, 138, 0.85)');
    },
  },
  {
    name: 'Pixel',
    label: '픽셀',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = INK;
      const s = w * 0.055;
      const bx = x + w * 0.34;
      const by = y + h * 0.68;
      ctx.fillRect(bx, by, s, s);
      ctx.fillRect(bx + s * 5, by, s, s);
      ctx.fillRect(bx + s, by + s, s * 4, s);
    },
  },
];

// --------------------------------------------------------------------------
// DETAIL1 — 얼굴 위에 얹는 디테일
// --------------------------------------------------------------------------

export const DETAILS: PartOption[] = [
  { name: 'None', label: '없음', draw: () => {} },
  {
    name: 'Blush',
    label: '홍조',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.25, y + h * 0.6, w * 0.08, 'rgba(255, 120, 160, 0.6)');
      disc(ctx, x + w * 0.75, y + h * 0.6, w * 0.08, 'rgba(255, 120, 160, 0.6)');
    },
  },
  {
    name: 'Bow',
    label: '리본',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.2, y + h * 0.15],
          [x + w * 0.4, y + h * 0.25],
          [x + w * 0.2, y + h * 0.35],
        ],
        '#ff4a9e',
      );
      disc(ctx, x + w * 0.1, y + h * 0.25, w * 0.05, '#ff4a9e');
    },
  },
  {
    name: 'Hat',
    label: '모자',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#333';
      ctx.fillRect(x + w * 0.2, y, w * 0.6, h * 0.15);
      ctx.fillRect(x + w * 0.1, y + h * 0.1, w * 0.8, h * 0.05);
    },
  },
  {
    name: 'Mustache',
    label: '콧수염',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#222';
      ctx.beginPath();
      ctx.arc(x + w * 0.4, y + h * 0.72, w * 0.12, Math.PI, 0);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.6, y + h * 0.72, w * 0.12, Math.PI, 0);
      ctx.fill();
    },
  },
  {
    name: 'Freckles',
    label: '주근깨',
    draw: (ctx, x, y, w, h) => {
      const c = 'rgba(180, 100, 60, 0.75)';
      [
        [0.22, 0.58],
        [0.28, 0.63],
        [0.2, 0.66],
        [0.78, 0.58],
        [0.72, 0.63],
        [0.8, 0.66],
      ].forEach(([fx, fy]) => disc(ctx, x + w * fx, y + h * fy, w * 0.022, c));
    },
  },
  {
    name: 'Tear',
    label: '눈물',
    draw: (ctx, x, y, w, h) => drop(ctx, x + w * 0.3, y + h * 0.62, w * 0.05, 'rgba(120, 200, 255, 0.9)'),
  },
  {
    name: 'Tears',
    label: '펑펑',
    draw: (ctx, x, y, w, h) => {
      drop(ctx, x + w * 0.28, y + h * 0.63, w * 0.055, 'rgba(120, 200, 255, 0.9)');
      drop(ctx, x + w * 0.72, y + h * 0.63, w * 0.055, 'rgba(120, 200, 255, 0.9)');
    },
  },
  {
    name: 'Scar',
    label: '흉터',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.68, y + h * 0.24], [x + w * 0.82, y + h * 0.46]], lw(w) * 0.7, '#c04a4a');
      path(ctx, [[x + w * 0.68, y + h * 0.38], [x + w * 0.82, y + h * 0.3]], lw(w) * 0.7, '#c04a4a');
    },
  },
  {
    name: 'Bandaid',
    label: '반창고',
    draw: (ctx, x, y, w, h) => {
      ctx.save();
      ctx.translate(x + w * 0.72, y + h * 0.3);
      ctx.rotate(-0.5);
      ctx.fillStyle = '#ffd8a8';
      ctx.fillRect(-w * 0.12, -h * 0.045, w * 0.24, h * 0.09);
      ctx.fillStyle = 'rgba(150, 100, 50, 0.5)';
      for (let i = -1; i <= 1; i += 1) {
        ctx.fillRect(w * 0.02 * i - w * 0.01, -h * 0.02, w * 0.02, h * 0.04);
      }
      ctx.restore();
    },
  },
  {
    name: 'Beard',
    label: '턱수염',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#3a2f28';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.24, y + h * 0.62);
      ctx.quadraticCurveTo(x + w * 0.5, y + h * 1.08, x + w * 0.76, y + h * 0.62);
      ctx.quadraticCurveTo(x + w * 0.5, y + h * 0.78, x + w * 0.24, y + h * 0.62);
      ctx.fill();
    },
  },
  {
    name: 'Sweat',
    label: '식은땀',
    draw: (ctx, x, y, w, h) => {
      drop(ctx, x + w * 0.8, y + h * 0.22, w * 0.06, 'rgba(140, 210, 255, 0.95)');
      path(ctx, [[x + w * 0.86, y + h * 0.1], [x + w * 0.9, y + h * 0.18]], lw(w) * 0.5, 'rgba(140, 210, 255, 0.6)');
    },
  },
  {
    name: 'Eyepatch',
    label: '안대',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.1, y + h * 0.3], [x + w * 0.62, y + h * 0.36]], lw(w) * 0.6, '#1b1d26');
      ctx.fillStyle = '#1b1d26';
      ctx.beginPath();
      ctx.ellipse(x + w * 0.3, y + h * 0.45, w * 0.15, h * 0.12, -0.1, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  {
    name: 'BlushLines',
    label: '홍조선',
    draw: (ctx, x, y, w, h) => {
      const c = 'rgba(255, 110, 150, 0.85)';
      for (let i = 0; i < 3; i += 1) {
        const dx = w * 0.05 * i;
        path(ctx, [[x + w * 0.16 + dx, y + h * 0.66], [x + w * 0.21 + dx, y + h * 0.55]], lw(w) * 0.5, c);
        path(ctx, [[x + w * 0.68 + dx, y + h * 0.66], [x + w * 0.73 + dx, y + h * 0.55]], lw(w) * 0.5, c);
      }
    },
  },
  {
    name: 'Nose',
    label: '코',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.5, y + h * 0.52],
          [x + w * 0.56, y + h * 0.63],
          [x + w * 0.44, y + h * 0.63],
        ],
        'rgba(0, 0, 0, 0.45)',
      );
    },
  },
  {
    name: 'Mask',
    label: '마스크',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#e9eef7';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.2, y + h * 0.56);
      ctx.lineTo(x + w * 0.8, y + h * 0.56);
      ctx.quadraticCurveTo(x + w * 0.5, y + h * 1.02, x + w * 0.2, y + h * 0.56);
      ctx.fill();
      path(ctx, [[x + w * 0.05, y + h * 0.5], [x + w * 0.22, y + h * 0.57]], lw(w) * 0.5, '#cfd6e4');
      path(ctx, [[x + w * 0.95, y + h * 0.5], [x + w * 0.78, y + h * 0.57]], lw(w) * 0.5, '#cfd6e4');
    },
  },
  {
    name: 'WarPaint',
    label: '워페인트',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = 'rgba(220, 40, 60, 0.75)';
      ctx.fillRect(x + w * 0.08, y + h * 0.52, w * 0.84, h * 0.05);
      ctx.fillRect(x + w * 0.14, y + h * 0.61, w * 0.72, h * 0.03);
    },
  },
  {
    name: 'Dimples',
    label: '보조개',
    draw: (ctx, x, y, w, h) => {
      disc(ctx, x + w * 0.29, y + h * 0.74, w * 0.022, 'rgba(0, 0, 0, 0.4)');
      disc(ctx, x + w * 0.71, y + h * 0.74, w * 0.022, 'rgba(0, 0, 0, 0.4)');
    },
  },
  {
    name: 'Stubble',
    label: '까칠수염',
    draw: (ctx, x, y, w, h) => {
      const c = 'rgba(40, 40, 50, 0.5)';
      for (let i = 0; i < 14; i += 1) {
        const a = Math.PI * (0.15 + (i / 13) * 0.7);
        const r = w * 0.4;
        disc(ctx, x + w * 0.5 + Math.cos(a) * r, y + h * 0.5 + Math.sin(a) * r, w * 0.018, c);
      }
    },
  },
  {
    name: 'Cyber',
    label: '사이버',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = 'rgba(0, 229, 255, 0.85)';
      ctx.fillRect(x + w * 0.58, y + h * 0.26, w * 0.28, h * 0.03);
      ctx.fillRect(x + w * 0.62, y + h * 0.33, w * 0.18, h * 0.02);
      disc(ctx, x + w * 0.9, y + h * 0.28, w * 0.025, 'rgba(0, 229, 255, 0.9)');
    },
  },
  {
    name: 'Snot',
    label: '콧물',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = 'rgba(150, 220, 120, 0.9)';
      ctx.beginPath();
      ctx.ellipse(x + w * 0.42, y + h * 0.63, w * 0.04, h * 0.06, 0, 0, Math.PI * 2);
      ctx.fill();
    },
  },
];

// --------------------------------------------------------------------------
// DETAIL2 — 머리 위 / 주변 액세서리
// --------------------------------------------------------------------------

export const DETAILS2: PartOption[] = [
  { name: 'None2', label: '없음', draw: () => {} },
  {
    name: 'Halo',
    label: '천사링',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#ffd43b';
      ctx.lineWidth = lw(w) * 0.8;
      ctx.beginPath();
      ctx.ellipse(x + w * 0.5, y - h * 0.12, w * 0.22, h * 0.06, 0, 0, Math.PI * 2);
      ctx.stroke();
    },
  },
  {
    name: 'Horns',
    label: '뿔',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.16, y + h * 0.14],
          [x + w * 0.3, y + h * 0.02],
          [x + w * 0.32, y + h * 0.2],
        ],
        '#e64a4a',
      );
      poly(
        ctx,
        [
          [x + w * 0.84, y + h * 0.14],
          [x + w * 0.7, y + h * 0.02],
          [x + w * 0.68, y + h * 0.2],
        ],
        '#e64a4a',
      );
    },
  },
  {
    name: 'Antenna',
    label: '더듬이',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.5, y + h * 0.06], [x + w * 0.56, y - h * 0.14]], lw(w) * 0.6, '#8b93b8');
      disc(ctx, x + w * 0.57, y - h * 0.17, w * 0.05, '#00e5ff');
    },
  },
  {
    name: 'Crown',
    label: '왕관',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.26, y + h * 0.1],
          [x + w * 0.26, y - h * 0.12],
          [x + w * 0.38, y - h * 0.02],
          [x + w * 0.5, y - h * 0.16],
          [x + w * 0.62, y - h * 0.02],
          [x + w * 0.74, y - h * 0.12],
          [x + w * 0.74, y + h * 0.1],
        ],
        '#ffd43b',
      );
      disc(ctx, x + w * 0.5, y + h * 0.03, w * 0.035, '#ff4a7d');
    },
  },
  {
    name: 'Cap',
    label: '야구모자',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#3b7dd8';
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.2, w * 0.34, Math.PI, 0);
      ctx.fill();
      ctx.fillStyle = '#2b5fa8';
      ctx.beginPath();
      ctx.ellipse(x + w * 0.74, y + h * 0.2, w * 0.22, h * 0.05, 0, Math.PI, 0);
      ctx.fill();
      disc(ctx, x + w * 0.5, y - h * 0.13, w * 0.03, '#2b5fa8');
    },
  },
  {
    name: 'Headphones',
    label: '헤드폰',
    draw: (ctx, x, y, w, h) => {
      curve(ctx, x + w * 0.5, y + h * 0.5, w * 0.56, Math.PI * 1.15, Math.PI * 1.85, lw(w) * 0.9, '#2f3446');
      ctx.fillStyle = '#2f3446';
      ctx.fillRect(x - w * 0.1, y + h * 0.34, w * 0.16, h * 0.22);
      ctx.fillRect(x + w * 0.94, y + h * 0.34, w * 0.16, h * 0.22);
      ctx.fillStyle = '#00e5ff';
      ctx.fillRect(x - w * 0.06, y + h * 0.4, w * 0.03, h * 0.1);
      ctx.fillRect(x + w * 1.03, y + h * 0.4, w * 0.03, h * 0.1);
    },
  },
  {
    name: 'Flower',
    label: '꽃',
    draw: (ctx, x, y, w, h) => {
      const cx = x + w * 0.78;
      const cy = y + h * 0.06;
      for (let i = 0; i < 5; i += 1) {
        const a = (Math.PI * 2 * i) / 5;
        disc(ctx, cx + Math.cos(a) * w * 0.07, cy + Math.sin(a) * w * 0.07, w * 0.05, '#ff8fc8');
      }
      disc(ctx, cx, cy, w * 0.04, '#ffd43b');
    },
  },
  {
    name: 'Sparkles',
    label: '반짝임',
    draw: (ctx, x, y, w, h) => {
      star(ctx, x + w * 0.14, y + h * 0.12, w * 0.07, '#ffd43b', 4);
      star(ctx, x + w * 0.86, y + h * 0.06, w * 0.05, '#fff2a8', 4);
      star(ctx, x + w * 0.68, y - h * 0.1, w * 0.04, '#ffd43b', 4);
    },
  },
  {
    name: 'CatEars',
    label: '고양이귀',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.14, y + h * 0.2],
          [x + w * 0.2, y - h * 0.08],
          [x + w * 0.42, y + h * 0.08],
        ],
        '#2f3446',
      );
      poly(
        ctx,
        [
          [x + w * 0.86, y + h * 0.2],
          [x + w * 0.8, y - h * 0.08],
          [x + w * 0.58, y + h * 0.08],
        ],
        '#2f3446',
      );
      poly(
        ctx,
        [
          [x + w * 0.21, y + h * 0.16],
          [x + w * 0.23, y + h * 0.02],
          [x + w * 0.34, y + h * 0.11],
        ],
        '#ff8fc8',
      );
      poly(
        ctx,
        [
          [x + w * 0.79, y + h * 0.16],
          [x + w * 0.77, y + h * 0.02],
          [x + w * 0.66, y + h * 0.11],
        ],
        '#ff8fc8',
      );
    },
  },
  {
    name: 'BunnyEars',
    label: '토끼귀',
    draw: (ctx, x, y, w, h) => {
      ellipse(ctx, x + w * 0.36, y - h * 0.1, w * 0.07, h * 0.2, '#f4f6ff', -0.15);
      ellipse(ctx, x + w * 0.64, y - h * 0.1, w * 0.07, h * 0.2, '#f4f6ff', 0.15);
      ellipse(ctx, x + w * 0.36, y - h * 0.1, w * 0.035, h * 0.13, '#ffb3cd', -0.15);
      ellipse(ctx, x + w * 0.64, y - h * 0.1, w * 0.035, h * 0.13, '#ffb3cd', 0.15);
    },
  },
  {
    name: 'Propeller',
    label: '프로펠러',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#ff6b6b';
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.16, w * 0.26, Math.PI, 0);
      ctx.fill();
      path(ctx, [[x + w * 0.5, y - h * 0.1], [x + w * 0.5, y + h * 0.02]], lw(w) * 0.5, '#8b93b8');
      ellipse(ctx, x + w * 0.36, y - h * 0.12, w * 0.13, h * 0.03, '#4dabf7');
      ellipse(ctx, x + w * 0.64, y - h * 0.12, w * 0.13, h * 0.03, '#4dabf7');
    },
  },
  {
    name: 'Bandana',
    label: '두건',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#e64a4a';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.06, y + h * 0.3);
      ctx.quadraticCurveTo(x + w * 0.5, y + h * 0.06, x + w * 0.94, y + h * 0.3);
      ctx.quadraticCurveTo(x + w * 0.5, y + h * 0.2, x + w * 0.06, y + h * 0.3);
      ctx.fill();
      poly(
        ctx,
        [
          [x + w * 0.9, y + h * 0.26],
          [x + w * 1.06, y + h * 0.36],
          [x + w * 0.92, y + h * 0.4],
        ],
        '#c03838',
      );
    },
  },
  {
    name: 'Ahoge',
    label: '삐친머리',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#3a2f28';
      ctx.lineWidth = lw(w) * 0.8;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.48, y + h * 0.04);
      ctx.quadraticCurveTo(x + w * 0.42, y - h * 0.2, x + w * 0.66, y - h * 0.16);
      ctx.stroke();
    },
  },
  {
    name: 'Sprout',
    label: '새싹',
    draw: (ctx, x, y, w, h) => {
      path(ctx, [[x + w * 0.5, y + h * 0.04], [x + w * 0.5, y - h * 0.14]], lw(w) * 0.6, '#4f9b4f');
      ellipse(ctx, x + w * 0.4, y - h * 0.14, w * 0.09, h * 0.05, '#5cb85c', -0.4);
      ellipse(ctx, x + w * 0.6, y - h * 0.16, w * 0.09, h * 0.05, '#5cb85c', 0.4);
    },
  },
  {
    name: 'TopHat',
    label: '실크햇',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#22252f';
      ctx.fillRect(x + w * 0.3, y - h * 0.22, w * 0.4, h * 0.28);
      ctx.fillRect(x + w * 0.14, y + h * 0.04, w * 0.72, h * 0.05);
      ctx.fillStyle = '#e64a4a';
      ctx.fillRect(x + w * 0.3, y - h * 0.02, w * 0.4, h * 0.05);
    },
  },
  {
    name: 'PartyHat',
    label: '고깔',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.5, y - h * 0.26],
          [x + w * 0.7, y + h * 0.1],
          [x + w * 0.3, y + h * 0.1],
        ],
        '#7c5cff',
      );
      path(ctx, [[x + w * 0.38, y - h * 0.04], [x + w * 0.62, y - h * 0.04]], lw(w) * 0.5, '#ffd43b');
      disc(ctx, x + w * 0.5, y - h * 0.28, w * 0.05, '#ffd43b');
    },
  },
  {
    name: 'Question',
    label: '물음표',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#ffd43b';
      ctx.font = `bold ${w * 0.3}px ${'system-ui, sans-serif'}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('?', x + w * 0.8, y - h * 0.06);
    },
  },
  {
    name: 'AngerVein',
    label: '분노마크',
    draw: (ctx, x, y, w, h) => {
      const cx = x + w * 0.78;
      const cy = y + h * 0.14;
      const s = w * 0.07;
      const c = '#ff3b5c';
      path(ctx, [[cx - s, cy - s * 0.4], [cx, cy], [cx - s, cy + s * 0.4]], lw(w) * 0.6, c);
      path(ctx, [[cx + s, cy - s * 0.4], [cx, cy], [cx + s, cy + s * 0.4]], lw(w) * 0.6, c);
    },
  },
  {
    name: 'Flame',
    label: '불꽃',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#ff8c2b';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.5, y - h * 0.24);
      ctx.quadraticCurveTo(x + w * 0.74, y + h * 0.02, x + w * 0.5, y + h * 0.1);
      ctx.quadraticCurveTo(x + w * 0.26, y + h * 0.02, x + w * 0.5, y - h * 0.24);
      ctx.fill();
      ctx.fillStyle = '#ffd43b';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.5, y - h * 0.1);
      ctx.quadraticCurveTo(x + w * 0.62, y + h * 0.02, x + w * 0.5, y + h * 0.08);
      ctx.quadraticCurveTo(x + w * 0.38, y + h * 0.02, x + w * 0.5, y - h * 0.1);
      ctx.fill();
    },
  },
  {
    name: 'Wings',
    label: '날개',
    draw: (ctx, x, y, w, h) => {
      const wing = (dir: -1 | 1) => {
        ctx.fillStyle = 'rgba(240, 246, 255, 0.92)';
        ctx.beginPath();
        ctx.moveTo(x + w * (0.5 + dir * 0.44), y + h * 0.38);
        ctx.quadraticCurveTo(
          x + w * (0.5 + dir * 0.86),
          y + h * 0.18,
          x + w * (0.5 + dir * 0.78),
          y + h * 0.56,
        );
        ctx.quadraticCurveTo(
          x + w * (0.5 + dir * 0.66),
          y + h * 0.5,
          x + w * (0.5 + dir * 0.44),
          y + h * 0.38,
        );
        ctx.fill();
      };
      wing(-1);
      wing(1);
    },
  },
  {
    name: 'Hearts',
    label: '하트뿅',
    draw: (ctx, x, y, w, h) => {
      heart(ctx, x + w * 0.14, y + h * 0.1, w * 0.07, 'rgba(255, 74, 125, 0.9)');
      heart(ctx, x + w * 0.84, y - h * 0.02, w * 0.05, 'rgba(255, 74, 125, 0.7)');
    },
  },
  {
    name: 'Bolt',
    label: '번개',
    draw: (ctx, x, y, w, h) => {
      poly(
        ctx,
        [
          [x + w * 0.58, y - h * 0.24],
          [x + w * 0.42, y + h * 0.04],
          [x + w * 0.53, y + h * 0.04],
          [x + w * 0.44, y + h * 0.24],
          [x + w * 0.68, y - h * 0.06],
          [x + w * 0.55, y - h * 0.06],
        ],
        '#ffd43b',
      );
    },
  },
];

/** 몸통 색상 팔레트 (레거시 12종) */
export const COLORS: ColorOption[] = [
  { name: 'Red', label: '레드', val: '#ff6b6b' },
  { name: 'Teal', label: '틸', val: '#4ecdc4' },
  { name: 'Cyan', label: '시안', val: '#4cc9e8' },
  { name: 'Mint', label: '민트', val: '#9ad9bf' },
  { name: 'Cream', label: '크림', val: '#ffe8a3' },
  { name: 'Pink', label: '핑크', val: '#f06595' },
  { name: 'Seafoam', label: '씨폼', val: '#9bdccf' },
  { name: 'Yellow', label: '옐로', val: '#ffd43b' },
  { name: 'Purple', label: '퍼플', val: '#c08ad9' },
  { name: 'Blue', label: '블루', val: '#4dabf7' },
  { name: 'Orange', label: '오렌지', val: '#ffa94d' },
  { name: 'Green', label: '그린', val: '#51cf66' },
];

export const DEFAULT_COLOR = COLORS[0].val;
