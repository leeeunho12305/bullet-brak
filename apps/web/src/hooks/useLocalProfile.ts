// 닉네임 / 외형 / 코인 / 보유 아이템 localStorage 영속화.
// 레거시 키(bulletBrakCoins, bulletBrakOwnedItems)를 그대로 유지한다.
//
// 주의: gameStore 가 아래 순수 함수들을 import 하고, 이 파일의 훅은 gameStore 를
// import 한다(순환). 순수 함수는 전부 "function 선언"으로 두어 호이스팅되므로
// 어느 쪽이 먼저 평가돼도 안전하다.
import { useCallback, useState } from 'react';
import type { Customization, PartOffsets, PartSlot } from '@/types/game';
import { clampOffset, partPrice } from '@/game/avatars';
import { useGameStore } from '@/store/gameStore';

export const COINS_KEY = 'bulletBrakCoins';
export const OWNED_ITEMS_KEY = 'bulletBrakOwnedItems';
export const NICKNAME_KEY = 'bulletBrakNickname';
export const CUSTOMIZATION_KEY = 'bulletBrakCustomization';

/** 편집기의 파츠 카테고리 → localStorage 아이템 키 접두사(레거시 포맷 유지) */
export const SHOP_CATEGORY: Record<PartSlot, string> = {
  eye: 'eyes',
  mouth: 'mouths',
  detail: 'details',
  detail2: 'details2',
};

/** 위의 역방향. 상점 키만 들고 있는 곳에서 가격을 되찾을 때 쓴다. */
const SLOT_BY_SHOP: Record<string, PartSlot> = {
  eyes: 'eye',
  mouths: 'mouth',
  details: 'detail',
  details2: 'detail2',
};

/**
 * 상점 키 기준 가격(코인). 값은 파츠 등급에서 온다 —
 * 카탈로그가 등급 순으로 정렬돼 있어서 "뒤로 갈수록 예쁘고 비싸다".
 * 0이면 기본 제공이라 살 필요가 없다.
 */
export function itemPrice(category: string, index: number): number {
  const slot = SLOT_BY_SHOP[category];
  return slot ? partPrice(slot, index) : 0;
}

export type OwnedItems = Record<string, boolean>;

export interface LocalProfile {
  nickname: string;
  customization: Customization;
  coins: number;
}

export const DEFAULT_CUSTOMIZATION: Customization = {
  eye: 0,
  mouth: 0,
  detail: 0,
  detail2: 0,
  color: '#ff6b6b',
  offsets: {},
};

const PART_SLOTS: PartSlot[] = ['eye', 'mouth', 'detail', 'detail2'];

function readRaw(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeRaw(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 시크릿 모드 등에서 저장 실패는 무시 */
  }
}

/** 저장된 offsets 를 슬롯별로 정리한다. 모르는 키/잘못된 값은 버린다. */
function parseOffsets(raw: unknown): PartOffsets {
  if (!raw || typeof raw !== 'object') return {};
  const src = raw as Record<string, unknown>;
  const out: PartOffsets = {};
  for (const slot of PART_SLOTS) {
    const value = src[slot];
    if (!value || typeof value !== 'object') continue;
    const { x, y } = value as { x?: unknown; y?: unknown };
    const off = clampOffset({ x: Number(x), y: Number(y) });
    if (off.x !== 0 || off.y !== 0) out[slot] = off;
  }
  return out;
}

/** 저장된 값에서 Customization 을 안전하게 복구 */
function parseCustomization(raw: string | null): Customization {
  if (!raw) return { ...DEFAULT_CUSTOMIZATION };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return { ...DEFAULT_CUSTOMIZATION };
    const obj = parsed as Partial<Record<keyof Customization, unknown>>;
    return {
      eye: typeof obj.eye === 'number' ? obj.eye : 0,
      mouth: typeof obj.mouth === 'number' ? obj.mouth : 0,
      detail: typeof obj.detail === 'number' ? obj.detail : 0,
      // detail2 는 나중에 생긴 슬롯이라 예전 저장값에는 없다 → 0(없음)
      detail2: typeof obj.detail2 === 'number' ? obj.detail2 : 0,
      color: typeof obj.color === 'string' ? obj.color : DEFAULT_CUSTOMIZATION.color,
      offsets: parseOffsets(obj.offsets),
    };
  } catch {
    return { ...DEFAULT_CUSTOMIZATION };
  }
}

export function loadProfile(): LocalProfile {
  const coins = Number.parseInt(readRaw(COINS_KEY) ?? '', 10);
  return {
    nickname: readRaw(NICKNAME_KEY) ?? '',
    customization: parseCustomization(readRaw(CUSTOMIZATION_KEY)),
    coins: Number.isFinite(coins) ? coins : 0,
  };
}

export function saveNickname(value: string): void {
  writeRaw(NICKNAME_KEY, value);
}

export function saveCustomization(value: Customization): void {
  writeRaw(CUSTOMIZATION_KEY, JSON.stringify(value));
}

export function saveCoins(value: number): void {
  writeRaw(COINS_KEY, String(value));
}

export function loadOwnedItems(): OwnedItems {
  const raw = readRaw(OWNED_ITEMS_KEY);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const result: OwnedItems = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (value) result[key] = true;
    }
    return result;
  } catch {
    return {};
  }
}

export function saveOwnedItems(items: OwnedItems): void {
  writeRaw(OWNED_ITEMS_KEY, JSON.stringify(items));
}

/** 레거시와 동일한 키 포맷: "eyes:3" / "colors" 는 항상 무료 */
export function itemKey(category: string, index: number): string {
  return `${category}:${index}`;
}

export function isItemOwned(items: OwnedItems, category: string, index: number): boolean {
  if (category === 'colors') return true;
  if (itemPrice(category, index) <= 0) return true; // 0등급은 기본 제공
  return items[itemKey(category, index)] === true;
}

export interface UseLocalProfile extends LocalProfile {
  setNickname(value: string): void;
  setCustomization(value: Customization): void;
  setCoins(value: number): void;
  addCoins(delta: number): void;
  owned: OwnedItems;
  isOwned(category: string, index: number): boolean;
  /** 코인이 충분하면 구매하고 true. 부족하면 false. 가격은 등급에서 자동으로 온다. */
  buyItem(category: string, index: number, price?: number): boolean;
}

/**
 * 프로필은 store 가 단일 소스이고(setter 가 localStorage 도 갱신),
 * 보유 아이템만 이 훅의 로컬 state 로 관리한다.
 */
export function useLocalProfile(): UseLocalProfile {
  const nickname = useGameStore((s) => s.nickname);
  const customization = useGameStore((s) => s.customization);
  const coins = useGameStore((s) => s.coins);
  const setNickname = useGameStore((s) => s.setNickname);
  const setCustomization = useGameStore((s) => s.setCustomization);
  const setCoins = useGameStore((s) => s.setCoins);

  const [owned, setOwned] = useState<OwnedItems>(() => loadOwnedItems());

  const addCoins = useCallback(
    (delta: number) => {
      setCoins(useGameStore.getState().coins + delta);
    },
    [setCoins],
  );

  const isOwned = useCallback(
    (category: string, index: number) => isItemOwned(owned, category, index),
    [owned],
  );

  const buyItem = useCallback(
    (category: string, index: number, price = itemPrice(category, index)) => {
      if (isItemOwned(owned, category, index)) return true;
      const current = useGameStore.getState().coins;
      if (current < price) return false;
      const next: OwnedItems = { ...owned, [itemKey(category, index)]: true };
      saveOwnedItems(next);
      setOwned(next);
      setCoins(current - price);
      return true;
    },
    [owned, setCoins],
  );

  return {
    nickname,
    customization,
    coins,
    setNickname,
    setCustomization,
    setCoins,
    addCoins,
    owned,
    isOwned,
    buyItem,
  };
}
