// 전역 UI 상태(zustand). 60Hz 스냅샷은 여기 들어오지 않는다.
// 스냅샷은 net.latest 로만 흐르고, 이 store 에는 phase 가 "바뀔 때만" 반영된다.
import { create } from 'zustand';
import type {
  ChatMessage,
  Customization,
  Phase,
  PlayerSnap,
  RoomState,
  ServerMessage,
} from '@/types/game';
import {
  loadProfile,
  saveCoins,
  saveCustomization,
  saveNickname,
  saveOwnedItems,
} from '@/hooks/useLocalProfile';
import { pushProfileDebounced } from '@/api/identity';
import type { AccountResponse } from '@/api/client';

/** 채팅은 최근 30개만 유지 */
export const CHAT_LIMIT = 30;

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error';

export interface LastEvent {
  event: string;
  winner_id: string | null;
  loser_id: string | null;
}

/** 방금 방을 나간 사람. 알림을 띄우고 나면 지운다. */
export interface PlayerLeft {
  id: string;
  nickname: string;
  /** 그 사람이 나간 뒤 방에 남은 인원 */
  playersLeft: number;
}

export interface GameState {
  status: ConnectionStatus;
  error: string | null;
  playerId: string | null;
  room: RoomState | null;
  phase: Phase;
  chat: ChatMessage[];
  lastEvent: LastEvent | null;
  playerLeft: PlayerLeft | null;
  clearPlayerLeft(): void;

  // 프로필 (localStorage 동기화, 계정이 있으면 서버에도 반영)
  nickname: string;
  customization: Customization;
  coins: number;
  setNickname(v: string): void;
  setCustomization(v: Customization): void;
  setCoins(v: number): void;

  /**
   * 연결된 계정 id. null 이면 '로컬 모드'(서버에 DB 가 없거나 발급 실패).
   * 로컬 모드에서는 코인이 예전처럼 localStorage 권위라서 위조 가능하다.
   */
  accountId: string | null;
  /**
   * 부트스트랩이 끝났는데 계정을 못 받았다(= 진행이 이 브라우저에만 남는다).
   * accountId === null 만으로 판단하면 부팅 직후 잠깐 참이라 안내가 깜빡인다.
   */
  localOnly: boolean;
  /** 서버 계정을 프로필에 반영한다. 코인·소유 아이템은 서버 값이 이긴다. */
  applyAccount(account: AccountResponse): void;
  markLocalOnly(): void;

  // 내부 액션 (connection.ts 가 호출)
  applyServerMessage(msg: ServerMessage): void;
  setStatus(s: ConnectionStatus, error?: string | null): void;
  reset(): void;
}

const profile = loadProfile();

/** 세션(방) 관련 상태만 초기화. 프로필은 유지한다. */
function sessionDefaults(): Pick<
  GameState,
  'status' | 'error' | 'playerId' | 'room' | 'phase' | 'chat' | 'lastEvent' | 'playerLeft'
> {
  return {
    status: 'idle',
    error: null,
    playerId: null,
    room: null,
    phase: 'waiting',
    chat: [],
    lastEvent: null,
    playerLeft: null,
  };
}

export const useGameStore = create<GameState>()((set, get) => ({
  ...sessionDefaults(),

  nickname: profile.nickname,
  customization: profile.customization,
  coins: profile.coins,
  accountId: null,
  localOnly: false,

  setNickname(v) {
    saveNickname(v);
    set({ nickname: v });
    pushProfileDebounced({ nickname: v });
  },

  setCustomization(v) {
    saveCustomization(v);
    set({ customization: v });
    pushProfileDebounced({ customization: v });
  },

  setCoins(v) {
    const safe = Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0;
    saveCoins(safe);
    set({ coins: safe });
    // 코인은 올리지 않는다 — 서버가 정하는 값이라 클라이언트가 보낼 이유가 없다.
  },

  applyAccount(account) {
    // 코인은 서버가 권위다. localStorage 에도 캐시로 남겨 다음 부팅의 첫 화면을 맞춘다.
    saveCoins(account.coins);
    // 닉네임/아바타는 서버에 저장된 값으로 맞춘다(다른 기기에서 바꿨을 수 있다).
    saveNickname(account.nickname);
    saveCustomization(account.customization);
    // 구매가 서버로 넘어간 뒤로 보유 목록도 서버가 진실이다 — localStorage 는 캐시라
    // 합집합을 만들지 않고 그대로 덮는다(계정 발급 때 기존 아이템은 이미 이관됐다).
    const owned: Record<string, boolean> = {};
    for (const key of account.owned_items) owned[key] = true;
    saveOwnedItems(owned);
    set({
      accountId: account.id,
      localOnly: false,
      coins: account.coins,
      nickname: account.nickname,
      customization: account.customization,
    });
  },

  markLocalOnly() {
    set({ localOnly: true });
  },

  applyServerMessage(msg) {
    switch (msg.type) {
      case 'welcome': {
        set({
          status: 'connected',
          error: null,
          playerId: msg.player_id,
          room: msg.room,
          phase: msg.room.phase,
        });
        // 서버가 이번 입장을 계정에 묶었는지 알려준다. 부트스트랩은 성공했는데
        // 여기서 null 이 오면 토큰이 서버에 안 먹은 것이므로 그대로 반영한다.
        if (msg.account_id !== undefined) set({ accountId: msg.account_id });
        break;
      }

      case 'room_state': {
        set({ room: msg.room, phase: msg.room.phase });
        break;
      }

      case 'state': {
        // connection.ts 가 phase 변경 시에만 넘겨주지만, 안전하게 한 번 더 확인한다.
        const state = get();
        if (state.phase !== msg.phase) set({ phase: msg.phase });
        syncMyCoins(msg.players);
        break;
      }

      case 'chat': {
        const chat = [...get().chat, msg.message];
        set({ chat: chat.length > CHAT_LIMIT ? chat.slice(chat.length - CHAT_LIMIT) : chat });
        break;
      }

      case 'event': {
        set({
          lastEvent: {
            event: msg.event,
            winner_id: msg.winner_id,
            loser_id: msg.loser_id,
          },
        });
        break;
      }

      case 'player_left': {
        set({
          playerLeft: {
            id: msg.player_id,
            nickname: msg.nickname || '익명',
            playersLeft: msg.players_left,
          },
        });
        break;
      }

      case 'error': {
        set({ error: msg.message });
        break;
      }
    }
  },

  clearPlayerLeft() {
    if (get().playerLeft !== null) set({ playerLeft: null });
  },

  setStatus(s, error) {
    set({ status: s, error: error === undefined ? null : error });
  },

  reset() {
    set(sessionDefaults());
  },
}));

/**
 * 스냅샷의 내 코인을 프로필로 되돌려 저장(서버가 권위).
 * 구매는 로비(= 접속 전)에서만 일어나므로 구매 응답과 여기가 겹칠 일은 없다.
 */
function syncMyCoins(players: PlayerSnap[]): void {
  const state = useGameStore.getState();
  if (!state.playerId) return;
  const me = players.find((p) => p.id === state.playerId);
  if (!me || typeof me.coins !== 'number') return;
  if (me.coins !== state.coins) state.setCoins(me.coins);
}
