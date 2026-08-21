// 순수 캔버스 렌더러 — React 에 의존하지 않는다.
// renderFrame() 은 rAF 루프에서 매 프레임 호출된다. 객체 할당을 최소화한다.
import { BLAST_TICKS, MAX_CHARGE, WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { BotSnap, MapTheme, Platform, PlayerSnap, Snapshot, ZoneSnap } from '@/types/game';
import { drawAvatar } from './avatars';

const GRID = 40;
const TAU = Math.PI * 2;

/** 플레이어와 봇이 함께 쓰는 상태이상 필드(drawStatus 가 필요한 만큼만). */
type StatusSnap = Pick<PlayerSnap, 'silenced' | 'poison' | 'cold' | 'stunned'>;

/** 정지 충전(windup)을 쓰는 카드들 — 이 중 하나라도 있어야 집중 게이지를 그린다. */
const FOCUS_CARDS = new Set(['wind_up', 'careful_planning', 'ritual_countdown']);

/** 맵 정보가 아직 안 왔을 때 쓰는 기본 테마(= classic) */
const DEFAULT_THEME: MapTheme = {
  bg: '#0b0d17',
  grid: 'rgba(0, 229, 255, 0.055)',
  platform: '#1b2438',
  edge: 'rgba(0, 229, 255, 0.45)',
};

let theme: MapTheme = DEFAULT_THEME;

/** 맵이 바뀌면 GameCanvas 가 호출한다(room_state 로만 내려오는 값이라 rAF 밖에서 넣는다). */
export function setMapTheme(next: MapTheme | null | undefined): void {
  theme = next ?? DEFAULT_THEME;
}

/** 스냅샷이 아직 없을 때 캔버스를 칠할 색 */
export function backgroundColor(): string {
  return theme.bg;
}

/** 존 타입별 색상 */
const ZONE_COLORS: Record<string, string> = {
  heal: '#51cf66',
  toxic: '#a9e34b',
  frost: '#74c0fc',
  chilling: '#74c0fc',
  cold: '#74c0fc',
  emp: '#00c2ff',
  static: '#4dabf7',
  implode: '#b197fc',
  shockwave: '#b197fc',
  radiance: '#ffd43b',
};

interface Lerped {
  x: number;
  y: number;
}

interface Muzzle {
  x: number;
  y: number;
  angle: number;
  born: number;
}

/** 천장 충돌 먼지 한 알 */
interface Dust {
  x: number;
  y: number;
  vx: number;
  vy: number;
  born: number;
  life: number;
  size: number;
}

/** 천장 충돌 감지를 위해 기억해 두는 직전 스냅샷의 위치와 상승 속도 */
interface Seen {
  y: number;
  tick: number;
  /** 직전 구간에서 위로 올라온 속도(px/tick, 양수면 상승) */
  rise: number;
}

const lerped = new Map<string, Lerped>();
const muzzles: Muzzle[] = [];
const dusts: Dust[] = [];
const seen = new Map<string, Seen>();
let lastTime = 0;
let vignette: CanvasGradient | null = null;
let vignetteCtx: CanvasRenderingContext2D | null = null;

/** 라운드 시작 등 순간이동이 발생할 때 보간 상태를 비운다. */
export function resetInterpolation(): void {
  lerped.clear();
  muzzles.length = 0;
  dusts.length = 0;
  seen.clear();
  lastTime = 0;
}

/** 발사 순간의 총구 화염(로컬 이펙트). */
export function spawnMuzzleFlash(x: number, y: number, angle: number, now: number): void {
  if (muzzles.length > 8) muzzles.shift();
  muzzles.push({ x, y, angle, born: now });
}

// --------------------------------------------------------------------------
// 천장 충돌 먼지 (순수 로컬 이펙트 — 서버는 관여하지 않는다)
//
// 서버는 y<0 을 y=0 으로 끊기만 하고 "부딪혔다"는 이벤트를 보내지 않는다.
// 60Hz 스냅샷의 y 변화만으로 충분히 알아낼 수 있어서, 대역폭을 쓰지 않고 여기서 판정한다.
// --------------------------------------------------------------------------

/** 이 위쪽이면 천장에 붙은 것으로 본다(서버가 정확히 0 으로 붙인다) */
const CEILING_Y = 0.75;
/** 이보다 느리게 닿았으면 먼지를 내지 않는다 (px/tick) */
const MIN_IMPACT_SPEED = 5;
/** 먼지가 최대로 나는 충돌 속도 (px/tick) */
const FULL_IMPACT_SPEED = 26;
const MAX_DUST = 90;

function spawnCeilingDust(cx: number, strength: number, now: number): void {
  const count = Math.round(5 + strength * 8);
  for (let i = 0; i < count; i += 1) {
    if (dusts.length >= MAX_DUST) dusts.shift();
    // 천장을 따라 좌우로 퍼지면서 아주 조금씩 가라앉는다.
    const dir = i % 2 === 0 ? 1 : -1;
    const speed = (0.9 + Math.random() * 2.3) * (0.55 + strength * 0.8);
    dusts.push({
      x: cx + dir * Math.random() * 10,
      y: 2 + Math.random() * 5,
      vx: dir * (0.3 + Math.random() * 0.9) * speed,
      vy: Math.random() * 0.5 * speed,
      born: now,
      life: 360 + Math.random() * 260,
      size: 1.8 + Math.random() * 3.2,
    });
  }
}

/**
 * 엔티티가 이번 스냅샷에 천장을 "막 때렸는지" 보고, 그렇다면 먼지를 낸다.
 * 속도는 두 스냅샷의 y 차이로 잰다 — BotSnap 에는 vy 가 없어서 이 방법이 봇에도 통한다.
 */
function checkCeilingHit(id: string, cx: number, y: number, tick: number, now: number): void {
  const prev = seen.get(id);
  if (!prev || tick <= prev.tick) {
    if (!prev || tick !== prev.tick) seen.set(id, { y, tick, rise: 0 });
    return;
  }
  const rise = (prev.y - y) / (tick - prev.tick); // 이번 구간에서 올라온 속도
  seen.set(id, { y, tick, rise });

  // 직전엔 천장에서 떨어져 있다가 지금 붙은 순간에만 낸다(붙어 있는 내내 내면 안 된다).
  if (prev.y <= CEILING_Y || y > CEILING_Y) return;

  // 마지막 한 걸음은 천장에 잘려서 실제보다 짧다(예: 26px 로 날아와도 6.8px 만 남는다).
  // 잘리기 직전 구간의 속도를 같이 보고 더 빠른 쪽을 충돌 세기로 삼는다.
  const speed = Math.max(rise, prev.rise);
  if (speed < MIN_IMPACT_SPEED) return;
  spawnCeilingDust(cx, Math.min(1, speed / FULL_IMPACT_SPEED), now);
}

function drawDust(ctx: CanvasRenderingContext2D, now: number, dt: number): void {
  if (dusts.length === 0) return;
  const step = dt / 16.7;
  ctx.save();
  ctx.fillStyle = '#dfe6f5';
  for (let i = dusts.length - 1; i >= 0; i -= 1) {
    const d = dusts[i];
    const age = (now - d.born) / d.life;
    if (age >= 1) {
      dusts.splice(i, 1);
      continue;
    }
    d.x += d.vx * step;
    d.y += d.vy * step;
    d.vy += 0.055 * step; // 천천히 가라앉는다
    d.vx *= 0.965;
    const fade = 1 - age;
    ctx.globalAlpha = 0.5 * fade * fade;
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.size * (0.7 + age * 1.4), 0, TAU);
    ctx.fill();
  }
  ctx.restore();
}

function getVignette(ctx: CanvasRenderingContext2D): CanvasGradient {
  if (!vignette || vignetteCtx !== ctx) {
    const g = ctx.createRadialGradient(
      WORLD_WIDTH / 2,
      WORLD_HEIGHT / 2,
      120,
      WORLD_WIDTH / 2,
      WORLD_HEIGHT / 2,
      560,
    );
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(1, 'rgba(0,0,0,0.55)');
    vignette = g;
    vignetteCtx = ctx;
  }
  return vignette;
}

function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

  // 네온 그리드 (경로 1개로 한 번에 stroke)
  ctx.beginPath();
  for (let x = GRID; x < WORLD_WIDTH; x += GRID) {
    ctx.moveTo(x + 0.5, 0);
    ctx.lineTo(x + 0.5, WORLD_HEIGHT);
  }
  for (let y = GRID; y < WORLD_HEIGHT; y += GRID) {
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(WORLD_WIDTH, y + 0.5);
  }
  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = getVignette(ctx);
  ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

  drawArenaBounds(ctx);
}

/**
 * 좌우 벽과 천장. 서버에서 실제로 막혀 있는 면이다 — 플레이어도 탄환도 여기서 튕긴다.
 * 아무것도 그리지 않던 시절에는 "벽도 없는데 탄이 튕긴다"로 읽혔다. **아래쪽은 일부러
 * 비운다**: 바닥은 뚫려 있고(낙사) 서버도 그쪽으로 나간 탄환은 튕기지 않고 없앤다.
 */
function drawArenaBounds(ctx: CanvasRenderingContext2D): void {
  ctx.save();
  ctx.strokeStyle = theme.edge;
  ctx.globalAlpha = 0.5;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(1.5, WORLD_HEIGHT);
  ctx.lineTo(1.5, 1.5);
  ctx.lineTo(WORLD_WIDTH - 1.5, 1.5);
  ctx.lineTo(WORLD_WIDTH - 1.5, WORLD_HEIGHT);
  ctx.stroke();
  ctx.restore();
}

/** 블럭 종류별 강조색. types/game.ts 의 BLOCK_INFO 와 같은 색을 쓴다. */
const BLOCK_EDGE: Record<string, string> = {
  jump: '#51cf66',
  mover: '#4dabf7',
  ice: '#99e9f2',
  hazard: '#ff6b6b',
};

/** 점프대 화살표 / 가시 톱니 / 빙판 광택 — 종류를 한눈에 알아보게 하는 장식 */
function decorateBlock(ctx: CanvasRenderingContext2D, p: Platform, t: number): void {
  const kind = p.type;
  if (!kind || kind === 'solid') return;
  const color = BLOCK_EDGE[kind] ?? theme.edge;

  if (kind === 'jump') {
    // 위로 흐르는 쐐기 두 개. 밟으면 튄다는 걸 움직임으로 알린다.
    // 점프대는 바닥 안에 박혀 있으므로(서버 blocks.PASSABLE) 쐐기는 윗면 **위로** 띄운다.
    const cx = p.x + p.width / 2;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    for (let i = 0; i < 2; i += 1) {
      const phase = (t / 520 + i * 0.5) % 1;
      const top = p.y + 4 - phase * 22;
      ctx.globalAlpha = 0.35 + (1 - phase) * 0.5;
      ctx.beginPath();
      ctx.moveTo(cx - 9, top + 7);
      ctx.lineTo(cx, top);
      ctx.lineTo(cx + 9, top + 7);
      ctx.stroke();
    }
    ctx.restore();
    return;
  }

  if (kind === 'hazard') {
    // 윗면을 따라 늘어선 삼각 가시
    const step = 14;
    ctx.save();
    ctx.fillStyle = color;
    ctx.beginPath();
    for (let x = p.x; x + step <= p.x + p.width; x += step) {
      ctx.moveTo(x, p.y);
      ctx.lineTo(x + step / 2, p.y - 9);
      ctx.lineTo(x + step, p.y);
    }
    ctx.fill();
    ctx.restore();
    return;
  }

  if (kind === 'ice') {
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = color;
    ctx.fillRect(p.x, p.y, p.width, Math.min(4, p.height));
    ctx.restore();
    return;
  }

  if (kind === 'mover') {
    // 진행 축을 알리는 양방향 화살표
    const cx = p.x + p.width / 2;
    const cy = p.y + p.height / 2;
    const vertical = p.axis === 'y';
    const reach = vertical ? Math.min(10, p.height / 2 + 6) : Math.min(16, p.width / 2 - 4);
    if (reach < 5) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    for (const dir of [-1, 1]) {
      const ex = vertical ? cx : cx + reach * dir;
      const ey = vertical ? cy + reach * dir : cy;
      ctx.moveTo(cx, cy);
      ctx.lineTo(ex, ey);
      if (vertical) {
        ctx.moveTo(ex - 4, ey - 4 * dir);
        ctx.lineTo(ex, ey);
        ctx.lineTo(ex + 4, ey - 4 * dir);
      } else {
        ctx.moveTo(ex - 4 * dir, ey - 4);
        ctx.lineTo(ex, ey);
        ctx.lineTo(ex - 4 * dir, ey + 4);
      }
    }
    ctx.stroke();
    ctx.restore();
  }
}

function drawPlatforms(ctx: CanvasRenderingContext2D, snap: Snapshot, t: number): void {
  const list = snap.platforms;
  ctx.fillStyle = theme.platform;
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    ctx.fillRect(p.x, p.y, p.width, p.height);
  }

  // 일반 블럭은 맵 테마 색으로 한 번에, 특수 블럭만 자기 색으로 따로 그린다.
  ctx.save();
  ctx.lineWidth = 2;
  ctx.shadowBlur = 10;
  ctx.strokeStyle = theme.edge;
  ctx.shadowColor = theme.edge;
  ctx.beginPath();
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    if (p.type && p.type !== 'solid') continue;
    ctx.rect(p.x + 0.5, p.y + 0.5, p.width - 1, p.height - 1);
  }
  ctx.stroke();

  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    if (!p.type || p.type === 'solid') continue;
    const color = BLOCK_EDGE[p.type] ?? theme.edge;
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.globalAlpha = 0.22;
    ctx.fillStyle = color;
    ctx.fillRect(p.x, p.y, p.width, p.height);
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.rect(p.x + 0.5, p.y + 0.5, p.width - 1, p.height - 1);
    ctx.stroke();
  }
  ctx.restore();

  for (let i = 0; i < list.length; i += 1) {
    decorateBlock(ctx, list[i], t);
  }
}

/**
 * 폭발 섬광. 서버가 apply_explosion 마다 남기는 'blast' 장판을 그린다 —
 * 남은 틱(z.d)이 0 으로 줄어드는 동안 링이 퍼지면서 사라진다.
 * 게임 판정에는 전혀 관여하지 않는 순수 연출이다.
 */
function drawBlast(ctx: CanvasRenderingContext2D, z: ZoneSnap): void {
  const progress = Math.max(0, Math.min(1, 1 - (z.d ?? 0) / BLAST_TICKS));
  const fade = 1 - progress;
  const r = z.radius * (0.3 + 0.8 * progress);

  ctx.save();
  // 안쪽 섬광 — 하얗게 터졌다가 주황으로 식는다
  const glow = ctx.createRadialGradient(z.x, z.y, 0, z.x, z.y, r);
  glow.addColorStop(0, `rgba(255, 250, 220, ${0.9 * fade})`);
  glow.addColorStop(0.45, `rgba(255, 146, 43, ${0.5 * fade})`);
  glow.addColorStop(1, 'rgba(255, 80, 0, 0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(z.x, z.y, r, 0, TAU);
  ctx.fill();

  // 퍼지는 충격파 링
  ctx.globalAlpha = fade;
  ctx.strokeStyle = '#ffd8a8';
  ctx.lineWidth = 1 + 5 * fade;
  ctx.beginPath();
  ctx.arc(z.x, z.y, r, 0, TAU);
  ctx.stroke();

  // 사방으로 튀는 불티. 각도를 폭발 위치로 흩뜨려 매번 같은 모양이 되지 않게 한다.
  ctx.strokeStyle = `rgba(255, 212, 59, ${fade})`;
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (let i = 0; i < 8; i += 1) {
    const a = (i / 8) * TAU + z.x * 0.017 + z.y * 0.011;
    const inner = r * 0.72;
    const outer = r * (1.05 + 0.4 * progress);
    ctx.moveTo(z.x + Math.cos(a) * inner, z.y + Math.sin(a) * inner);
    ctx.lineTo(z.x + Math.cos(a) * outer, z.y + Math.sin(a) * outer);
  }
  ctx.stroke();
  ctx.restore();
}

/** 폭발은 캐릭터/탄환 위에 얹는다(가려지면 터진 걸 알 수 없다). */
function drawBlasts(ctx: CanvasRenderingContext2D, snap: Snapshot): void {
  const list = snap.zones;
  for (let i = 0; i < list.length; i += 1) {
    if (list[i].type === 'blast') drawBlast(ctx, list[i]);
  }
}

function drawZones(ctx: CanvasRenderingContext2D, snap: Snapshot, t: number): void {
  const list = snap.zones;
  if (list.length === 0) return;
  const pulse = 0.06 * Math.sin(t / 220);
  ctx.save();
  for (let i = 0; i < list.length; i += 1) {
    const z = list[i];
    if (z.type === 'blast') continue; // drawBlasts 가 맨 위에서 따로 그린다
    const color = ZONE_COLORS[z.type] ?? '#ff2e97';
    ctx.globalAlpha = 0.14 + pulse;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(z.x, z.y, z.radius, 0, TAU);
    ctx.fill();
    ctx.globalAlpha = 0.55;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.restore();
}

function drawBullets(ctx: CanvasRenderingContext2D, snap: Snapshot): void {
  const list = snap.bullets;
  if (list.length === 0) return;
  ctx.save();
  ctx.shadowBlur = 12;
  for (let i = 0; i < list.length; i += 1) {
    const b = list[i];
    const color = b.color || '#ffd43b';
    const size = b.size || 5;
    ctx.shadowColor = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(b.x, b.y, size, 0, TAU);
    ctx.fill();
  }
  ctx.shadowBlur = 0;
  ctx.globalAlpha = 0.85;
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  for (let i = 0; i < list.length; i += 1) {
    const b = list[i];
    ctx.beginPath();
    ctx.arc(b.x, b.y, Math.max(1, (b.size || 5) * 0.35), 0, TAU);
    ctx.fill();
  }
  ctx.restore();
}

function drawBar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  ratio: number,
  color: string,
): void {
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w * Math.max(0, Math.min(1, ratio)), h);
}

/**
 * 머리 위 가드 게이지. 이번 라운드에 남은 양이다(누르고 있는 동안만 줄어든다).
 * 가드를 펼치고 있는 동안에는 색이 밝아져서 지금 쓰고 있다는 걸 알린다.
 */
function drawGuard(ctx: CanvasRenderingContext2D, p: PlayerSnap, x: number, y: number, w: number): void {
  const ratio = p.block_meter / Math.max(1, p.block_meter_max);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(x, y, w, 3);
  drawBar(ctx, x, y, w, 3, ratio, p.blocking ? '#00e5ff' : '#4dabf7');
}

/** 상태이상(침묵/독/냉기) 표시 */
function drawStatus(ctx: CanvasRenderingContext2D, p: StatusSnap, cx: number, cy: number, r: number, t: number): void {
  if (p.cold) {
    ctx.save();
    ctx.globalAlpha = 0.28;
    ctx.fillStyle = '#74c0fc';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TAU);
    ctx.fill();
    ctx.restore();
  }
  if (p.poison > 0) {
    ctx.save();
    ctx.fillStyle = 'rgba(105, 219, 124, 0.85)';
    for (let i = 0; i < 3; i += 1) {
      const a = t / 320 + (i * TAU) / 3;
      const rr = r + 6 + Math.sin(t / 180 + i) * 3;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * 0.8, 2.6, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
  }
  if (p.silenced) {
    ctx.save();
    ctx.strokeStyle = 'rgba(180,180,190,0.8)';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.arc(cx, cy, r + 5, 0, TAU);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#dee2e6';
    ctx.fillText('🔇', cx + r + 8, cy - r);
    ctx.restore();
  }
  if (p.stunned) {
    // 머리 위를 도는 별 — 굳었다는 걸 한눈에 알리는 신호다.
    ctx.save();
    ctx.fillStyle = '#ffd43b';
    for (let i = 0; i < 3; i += 1) {
      const a = t / 140 + (i * TAU) / 3;
      ctx.globalAlpha = 0.55 + 0.45 * Math.sin(t / 120 + i);
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * (r + 3), cy - r - 8 + Math.sin(a) * 4, 2.4, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
  }
}

function drawPlayer(
  ctx: CanvasRenderingContext2D,
  p: PlayerSnap,
  lx: number,
  ly: number,
  isMe: boolean,
  t: number,
): void {
  const w = p.width;
  const h = p.height;
  const cx = lx + w / 2;
  const cy = ly + h / 2;
  const dead = !p.alive || p.hp <= 0;

  // 내 캐릭터 발밑 링
  if (isMe && !dead) {
    ctx.save();
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.85)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(cx, ly + h + 2, w * 0.55, h * 0.16, 0, 0, TAU);
    ctx.stroke();
    ctx.restore();
  }

  if (dead) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.PI / 2);
    drawAvatar(ctx, p.customization, -w / 2, -h / 2, w, h, { dead: true });
    ctx.restore();
    return;
  }

  drawAvatar(ctx, p.customization, lx, ly, w, h, { shadow: true });
  drawStatus(ctx, p, cx, cy, w / 2, t);

  const angle = Math.atan2(p.aim.y - cy, p.aim.x - cx);

  // 가드 원호 (조준 방향으로 펼쳐짐)
  if (p.blocking) {
    ctx.save();
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.9)';
    ctx.lineWidth = 4;
    ctx.shadowBlur = 12;
    ctx.shadowColor = 'rgba(0, 229, 255, 0.8)';
    ctx.beginPath();
    ctx.arc(cx, cy, w * 0.85, angle - 0.9, angle + 0.9);
    ctx.stroke();
    ctx.restore();
  }

  // 집중 게이지 (WIND UP / CAREFUL PLANNING / RITUAL COUNTDOWN) — 가만히 있으면 찬다
  if (p.windup > 0 && p.cards.some((c) => FOCUS_CARDS.has(c))) {
    const ratio = Math.max(0, Math.min(1, p.windup / MAX_CHARGE));
    ctx.save();
    ctx.strokeStyle = ratio >= 1 ? '#c0eb75' : 'rgba(192, 235, 117, 0.65)';
    ctx.lineWidth = 3;
    if (ratio >= 1) {
      ctx.shadowBlur = 10;
      ctx.shadowColor = '#c0eb75';
    }
    ctx.beginPath();
    ctx.arc(cx, cy, w * 0.95, -Math.PI / 2, -Math.PI / 2 + TAU * ratio);
    ctx.stroke();
    ctx.restore();
  }

  // 강공격 차징 링
  if (p.charging) {
    const ratio = Math.max(0, Math.min(1, p.charge / MAX_CHARGE));
    ctx.save();
    ctx.strokeStyle = ratio >= 1 ? '#ff2e97' : '#ffd43b';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, w * 0.72, -Math.PI / 2, -Math.PI / 2 + TAU * ratio);
    ctx.stroke();
    ctx.restore();
  }

  // 총구 라인
  ctx.strokeStyle = isMe ? 'rgba(0, 229, 255, 0.75)' : 'rgba(255,255,255,0.45)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(angle) * 30, cy + Math.sin(angle) * 30);
  ctx.stroke();

  // 머리 위 HP / 가드 / 닉네임
  const barY = ly - 14;
  drawBar(ctx, lx, barY, w, 6, p.hp / Math.max(1, p.max_hp), isMe ? '#00e5ff' : '#ff2e97');
  drawGuard(ctx, p, lx, barY + 8, w);

  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.font = 'bold 11px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(p.nickname || '익명', cx, barY - 6);
  ctx.textAlign = 'left';
}

function drawBot(ctx: CanvasRenderingContext2D, b: BotSnap, lx: number, ly: number, t: number): void {
  const dead = b.hp <= 0;
  if (dead) {
    ctx.save();
    ctx.translate(lx + b.width / 2, ly + b.height / 2);
    ctx.rotate(Math.PI / 2);
    drawAvatar(ctx, b.customization, -b.width / 2, -b.height / 2, b.width, b.height, { dead: true });
    ctx.restore();
    return;
  }
  drawAvatar(ctx, b.customization, lx, ly, b.width, b.height, { shadow: true });
  drawStatus(ctx, b, lx + b.width / 2, ly + b.height / 2, b.width / 2, t);
  drawBar(ctx, lx, ly - 12, b.width, 5, b.hp / Math.max(1, b.max_hp), '#ff6b6b');
}

function drawMuzzles(ctx: CanvasRenderingContext2D, now: number): void {
  for (let i = muzzles.length - 1; i >= 0; i -= 1) {
    const m = muzzles[i];
    const life = 1 - (now - m.born) / 140;
    if (life <= 0) {
      muzzles.splice(i, 1);
      continue;
    }
    ctx.save();
    ctx.globalAlpha = life;
    ctx.fillStyle = '#ffb347';
    ctx.beginPath();
    ctx.arc(m.x + Math.cos(m.angle) * 6, m.y + Math.sin(m.angle) * 6, 4 + life * 7, 0, TAU);
    ctx.fill();
    ctx.restore();
  }
}

/** 스냅샷 좌표를 향해 지수 보간한 좌표를 얻는다. */
function smooth(id: string, x: number, y: number, a: number): Lerped {
  let l = lerped.get(id);
  if (!l) {
    l = { x, y };
    lerped.set(id, l);
    return l;
  }
  // 순간이동(리스폰 등)은 보간하지 않는다.
  if (Math.abs(x - l.x) > 220 || Math.abs(y - l.y) > 220) {
    l.x = x;
    l.y = y;
    return l;
  }
  l.x += (x - l.x) * a;
  l.y += (y - l.y) * a;
  return l;
}

/**
 * 한 프레임을 그린다.
 * @param t rAF 타임스탬프(ms)
 */
export function renderFrame(
  ctx: CanvasRenderingContext2D,
  snap: Snapshot,
  myId: string | null,
  t: number,
): void {
  const dt = lastTime === 0 ? 16.7 : Math.min(120, t - lastTime);
  lastTime = t;
  const alpha = 1 - Math.pow(1 - 0.35, dt / 16.7);

  drawBackground(ctx);
  drawZones(ctx, snap, t);
  drawPlatforms(ctx, snap, t);
  drawBullets(ctx, snap);

  const bots = snap.bots;
  for (let i = 0; i < bots.length; i += 1) {
    const b = bots[i];
    const l = smooth(b.id, b.x, b.y, alpha);
    checkCeilingHit(b.id, l.x + b.width / 2, b.y, snap.tick, t);
    drawBot(ctx, b, l.x, l.y, t);
  }

  const players = snap.players;
  for (let i = 0; i < players.length; i += 1) {
    const p = players[i];
    const l = smooth(p.id, p.x, p.y, alpha);
    checkCeilingHit(p.id, l.x + p.width / 2, p.y, snap.tick, t);
    drawPlayer(ctx, p, l.x, l.y, p.id === myId, t);
  }

  // 먼지·폭발은 캐릭터 위에 얹는다(천장에 붙어 있거나 몸에 가려도 보여야 한다).
  drawBlasts(ctx, snap);
  drawDust(ctx, t, dt);
  drawMuzzles(ctx, t);
}
