// 맵 에디터로 짠 배치를 이 브라우저에 보관한다. 방을 나갔다 들어와도, 다음에 접속해도
// 그대로 다시 불러올 수 있다. 서버에는 "저장하고 적용"을 눌렀을 때만 올라간다.
import { WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { BlockType, Platform } from '@/types/game';

const KEY = 'bulletbrak.layouts.v1';
/** 슬롯 개수 상한(오래된 것부터 밀려난다) */
const MAX_SLOTS = 20;

export interface SavedLayout {
  name: string;
  /** 어느 맵에서 짠 배치인지(목록에 표시만 한다 — 다른 맵에도 불러올 수 있다) */
  map: string;
  blocks: Platform[];
  /** 저장 시각(ms). 최신순 정렬에 쓴다. */
  at: number;
}

const KINDS: BlockType[] = ['solid', 'jump', 'mover', 'ice', 'hazard'];

function num(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** localStorage 는 사람이 고칠 수 있는 곳이다. 읽을 때마다 모양을 확인한다. */
function readBlock(raw: unknown): Platform | null {
  if (!raw || typeof raw !== 'object') return null;
  const src = raw as Record<string, unknown>;
  const width = num(src.width);
  const height = num(src.height);
  if (width <= 0 || height <= 0 || width > WORLD_WIDTH || height > WORLD_HEIGHT) return null;
  const kind = KINDS.includes(src.type as BlockType) ? (src.type as BlockType) : 'solid';
  const block: Platform = { x: num(src.x), y: num(src.y), width, height, type: kind };
  if (kind === 'jump') block.power = num(src.power, 21);
  if (kind === 'mover') {
    block.axis = src.axis === 'y' ? 'y' : 'x';
    block.span = num(src.span, 120);
    block.speed = num(src.speed, 0.9);
  }
  return block;
}

function readSlot(raw: unknown): SavedLayout | null {
  if (!raw || typeof raw !== 'object') return null;
  const src = raw as Record<string, unknown>;
  const name = typeof src.name === 'string' ? src.name.trim() : '';
  if (!name) return null;
  const blocks = Array.isArray(src.blocks)
    ? src.blocks.map(readBlock).filter((b): b is Platform => b !== null)
    : [];
  if (blocks.length === 0) return null;
  return {
    name,
    map: typeof src.map === 'string' ? src.map : '',
    blocks,
    at: num(src.at),
  };
}

/** 저장된 배치를 최신순으로. 저장소를 못 쓰면 빈 목록. */
export function listLayouts(): SavedLayout[] {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return []; // 사생활 보호 모드 등 — 저장 기능만 조용히 꺼진다
  }
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(readSlot)
      .filter((s): s is SavedLayout => s !== null)
      .sort((a, b) => b.at - a.at);
  } catch {
    return [];
  }
}

function write(list: SavedLayout[]): SavedLayout[] {
  const kept = list.slice(0, MAX_SLOTS);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    // 용량 초과/차단. 화면에는 방금 저장한 것으로 보이지만 다음 접속에는 남지 않는다.
  }
  return kept;
}

/** 같은 이름이면 덮어쓴다. 저장 뒤의 목록을 돌려준다. */
export function saveLayout(name: string, map: string, blocks: Platform[]): SavedLayout[] {
  const trimmed = name.trim().slice(0, 24);
  if (!trimmed || blocks.length === 0) return listLayouts();
  const slot: SavedLayout = { name: trimmed, map, blocks, at: Date.now() };
  return write([slot, ...listLayouts().filter((s) => s.name !== trimmed)]);
}

export function deleteLayout(name: string): SavedLayout[] {
  return write(listLayouts().filter((s) => s.name !== name));
}
