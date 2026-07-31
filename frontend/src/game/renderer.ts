// 순수 캔버스 렌더러 — React 에 의존하지 않는다.
// renderFrame() 은 rAF 루프에서 매 프레임 호출된다. 객체 할당을 최소화한다.
import { MAX_CHARGE, WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { BotSnap, PlayerSnap, Snapshot } from '@/types/game';
import { drawAvatar } from './avatars';

const GRID = 40;
const TAU = Math.PI * 2;

/** 존 타입별 색상 */
const ZONE_COLORS: Record<string, string> = {
  heal: '#51cf66',
  toxic: '#a9e34b',
  frost: '#74c0fc',
  chilling: '#74c0fc',
  cold: '#74c0fc',
  emp: '#4dabf7',
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

const lerped = new Map<string, Lerped>();
const muzzles: Muzzle[] = [];
let lastTime = 0;
let vignette: CanvasGradient | null = null;
let vignetteCtx: CanvasRenderingContext2D | null = null;

/** 라운드 시작 등 순간이동이 발생할 때 보간 상태를 비운다. */
export function resetInterpolation(): void {
  lerped.clear();
  muzzles.length = 0;
  lastTime = 0;
}

/** 발사 순간의 총구 화염(로컬 이펙트). */
export function spawnMuzzleFlash(x: number, y: number, angle: number, now: number): void {
  if (muzzles.length > 8) muzzles.shift();
  muzzles.push({ x, y, angle, born: now });
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
  ctx.fillStyle = '#0b0f1a';
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
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.055)';
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = getVignette(ctx);
  ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
}

function drawPlatforms(ctx: CanvasRenderingContext2D, snap: Snapshot): void {
  const list = snap.platforms;
  ctx.fillStyle = '#1b2438';
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    ctx.fillRect(p.x, p.y, p.width, p.height);
  }
  ctx.save();
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.45)';
  ctx.lineWidth = 2;
  ctx.shadowBlur = 10;
  ctx.shadowColor = 'rgba(0, 229, 255, 0.6)';
  ctx.beginPath();
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i];
    ctx.rect(p.x + 0.5, p.y + 0.5, p.width - 1, p.height - 1);
  }
  ctx.stroke();
  ctx.restore();
}

function drawZones(ctx: CanvasRenderingContext2D, snap: Snapshot, t: number): void {
  const list = snap.zones;
  if (list.length === 0) return;
  const pulse = 0.06 * Math.sin(t / 220);
  ctx.save();
  for (let i = 0; i < list.length; i += 1) {
    const z = list[i];
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

/** 상태이상(침묵/독/냉기) 표시 */
function drawStatus(ctx: CanvasRenderingContext2D, p: PlayerSnap, cx: number, cy: number, r: number, t: number): void {
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
  if (p.blocking && p.block_meter > 0) {
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
  drawBar(ctx, lx, barY + 8, w, 3, p.block_meter / Math.max(1, p.block_meter_max), '#4dabf7');

  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.font = 'bold 11px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(p.nickname || '익명', cx, barY - 6);
  ctx.textAlign = 'left';
}

function drawBot(ctx: CanvasRenderingContext2D, b: BotSnap, lx: number, ly: number): void {
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
  drawPlatforms(ctx, snap);
  drawBullets(ctx, snap);

  const bots = snap.bots;
  for (let i = 0; i < bots.length; i += 1) {
    const b = bots[i];
    const l = smooth(b.id, b.x, b.y, alpha);
    drawBot(ctx, b, l.x, l.y);
  }

  const players = snap.players;
  for (let i = 0; i < players.length; i += 1) {
    const p = players[i];
    const l = smooth(p.id, p.x, p.y, alpha);
    drawPlayer(ctx, p, l.x, l.y, p.id === myId, t);
  }

  drawMuzzles(ctx, t);
}
