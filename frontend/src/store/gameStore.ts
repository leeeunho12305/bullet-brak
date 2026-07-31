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
import { loadProfile, saveCoins, saveCustomization, saveNickname } from '@/hooks/useLocalProfile';

/** 채팅은 최근 30개만 유지 */
export const CHAT_LIMIT = 30;

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error';

export interface LastEvent {
  event: string;
  winner_id: string | null;
  loser_id: string | null;
}

export interface GameState {
  status: ConnectionStatus;
  error: string | null;
  playerId: string | null;
  room: RoomState | null;
  phase: Phase;
  chat: ChatMessage[];
  lastEvent: LastEvent | null;

  // 프로필 (localStorage 동기화)
  nickname: string;
  customization: Customization;
  coins: number;
  setNickname(v: string): void;
  setCustomization(v: Customization): void;
  setCoins(v: number): void;

  // 내부 액션 (connection.ts 가 호출)
  applyServerMessage(msg: ServerMessage): void;
  setStatus(s: ConnectionStatus, error?: string | null): void;
  reset(): void;
}

const profile = loadProfile();

/** 세션(방) 관련 상태만 초기화. 프로필은 유지한다. */
function sessionDefaults(): Pick<
  GameState,
  'status' | 'error' | 'playerId' | 'room' | 'phase' | 'chat' | 'lastEvent'
> {
  return {
    status: 'idle',
    error: null,
    playerId: null,
    room: null,
    phase: 'waiting',
    chat: [],
    lastEvent: null,
  };
}

export const useGameStore = create<GameState>()((set, get) => ({
  ...sessionDefaults(),

  nickname: profile.nickname,
  customization: profile.customization,
  coins: profile.coins,

  setNickname(v) {
    saveNickname(v);
    set({ nickname: v });
  },

  setCustomization(v) {
    saveCustomization(v);
    set({ customization: v });
  },

  setCoins(v) {
    const safe = Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0;
    saveCoins(safe);
    set({ coins: safe });
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

      case 'error': {
        set({ error: msg.message });
        break;
      }
    }
  },

  setStatus(s, error) {
    set({ status: s, error: error === undefined ? null : error });
  },

  reset() {
    set(sessionDefaults());
  },
}));

/** 스냅샷의 내 코인을 프로필로 되돌려 저장(서버가 권위) */
function syncMyCoins(players: PlayerSnap[]): void {
  const state = useGameStore.getState();
  if (!state.playerId) return;
  const me = players.find((p) => p.id === state.playerId);
  if (!me || typeof me.coins !== 'number') return;
  if (me.coins !== state.coins) state.setCoins(me.coins);
}
