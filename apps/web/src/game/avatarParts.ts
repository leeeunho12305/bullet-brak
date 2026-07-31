// 레거시 client/src/app.js 의 options(eyes/mouths/details/colors) 배열을 그대로 이식했다.
// 모든 draw 는 (x, y, w, h) 사각형 안에 파츠를 그린다. 좌표는 비율 기반이라 크기와 무관하다.

export type PartDraw = (
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) => void;

export interface PartOption {
  /** 내부 식별용 이름 */
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

/** 눈 5종 */
export const EYES: PartOption[] = [
  {
    name: 'Normal',
    label: '기본',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.arc(x + w * 0.3, y + h * 0.45, w * 0.08, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.7, y + h * 0.45, w * 0.08, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  {
    name: 'Angry',
    label: '분노',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + w * 0.2, y + h * 0.35);
      ctx.lineTo(x + w * 0.4, y + h * 0.45);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + w * 0.8, y + h * 0.35);
      ctx.lineTo(x + w * 0.6, y + h * 0.45);
      ctx.stroke();
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.arc(x + w * 0.3, y + h * 0.5, w * 0.06, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.7, y + h * 0.5, w * 0.06, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  {
    name: 'Cute',
    label: '귀염',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.arc(x + w * 0.3, y + h * 0.45, w * 0.1, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.7, y + h * 0.45, w * 0.1, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.arc(x + w * 0.28, y + h * 0.43, w * 0.03, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.68, y + h * 0.43, w * 0.03, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  {
    name: 'Dead',
    label: 'X눈',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + w * 0.2, y + h * 0.4);
      ctx.lineTo(x + w * 0.4, y + h * 0.5);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + w * 0.4, y + h * 0.4);
      ctx.lineTo(x + w * 0.2, y + h * 0.5);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + w * 0.6, y + h * 0.4);
      ctx.lineTo(x + w * 0.8, y + h * 0.5);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + w * 0.8, y + h * 0.4);
      ctx.lineTo(x + w * 0.6, y + h * 0.5);
      ctx.stroke();
    },
  },
  {
    name: 'Cool',
    label: '선글',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#000';
      ctx.fillRect(x + w * 0.15, y + h * 0.4, w * 0.7, h * 0.1);
    },
  },
];

/** 입 5종 */
export const MOUTHS: PartOption[] = [
  {
    name: 'Smile',
    label: '미소',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.6, w * 0.2, 0.1 * Math.PI, 0.9 * Math.PI);
      ctx.stroke();
    },
  },
  {
    name: 'Flat',
    label: '무표정',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + w * 0.35, y + h * 0.75);
      ctx.lineTo(x + w * 0.65, y + h * 0.75);
      ctx.stroke();
    },
  },
  {
    name: 'O',
    label: '동그라미',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x + w * 0.5, y + h * 0.75, w * 0.08, 0, Math.PI * 2);
      ctx.stroke();
    },
  },
  {
    name: 'Cat',
    label: '고양이',
    draw: (ctx, x, y, w, h) => {
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x + w * 0.4, y + h * 0.7, w * 0.1, 0, Math.PI);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x + w * 0.6, y + h * 0.7, w * 0.1, 0, Math.PI);
      ctx.stroke();
    },
  },
  {
    name: 'Grin',
    label: '이빨',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#fff';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.rect(x + w * 0.35, y + h * 0.7, w * 0.3, h * 0.12);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + w * 0.35, y + h * 0.76);
      ctx.lineTo(x + w * 0.65, y + h * 0.76);
      ctx.stroke();
    },
  },
];

/** 디테일 5종 */
export const DETAILS: PartOption[] = [
  { name: 'None', label: '없음', draw: () => {} },
  {
    name: 'Blush',
    label: '홍조',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = 'rgba(255, 120, 160, 0.6)';
      ctx.beginPath();
      ctx.arc(x + w * 0.25, y + h * 0.6, w * 0.08, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.75, y + h * 0.6, w * 0.08, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  {
    name: 'Bow',
    label: '리본',
    draw: (ctx, x, y, w, h) => {
      ctx.fillStyle = '#ff4a9e';
      ctx.beginPath();
      ctx.moveTo(x + w * 0.2, y + h * 0.15);
      ctx.lineTo(x + w * 0.4, y + h * 0.25);
      ctx.lineTo(x + w * 0.2, y + h * 0.35);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x + w * 0.1, y + h * 0.25, w * 0.05, 0, Math.PI * 2);
      ctx.fill();
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
