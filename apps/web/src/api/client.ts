// REST 클라이언트 — docs/PROTOCOL.md §1
import type { CardInfo, Customization, MapInfo, Mode, Phase } from '@/types/game';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export interface HealthResponse {
  status: string;
  /** 'off' 면 서버에 DB 가 없다 = 계정 기능 없이 localStorage 로만 동작한다. */
  db: 'on' | 'off';
}

/** 서버가 인정하는 내 프로필. 코인·소유 아이템의 유일한 진실이다. */
export interface AccountResponse {
  id: string;
  nickname: string;
  customization: Customization;
  coins: number;
  level: number;
  xp: number;
  matches_played: number;
  matches_won: number;
  owned_items: string[];
}

export interface CreateAnonAccountBody {
  nickname?: string;
  customization?: Customization;
  /** localStorage 시절 잔액 이관용. 서버가 상한으로 자른다. */
  seed_coins?: number;
  seed_items?: string[];
}

export interface CreateAnonAccountResponse {
  /** 평문 토큰. 서버는 해시만 저장하므로 여기서 잃으면 계정도 잃는다. */
  token: string;
  account: AccountResponse;
}

export interface UpdateProfileBody {
  nickname?: string;
  customization?: Customization;
}

/** 구매 실패 사유. 서버가 새 값을 추가해도 클라이언트가 죽지 않게 string 도 받는다. */
export type BuyItemReason =
  | 'ok'
  | 'already_owned'
  | 'insufficient_coins'
  | 'invalid_item'
  | (string & {});

/**
 * 구매 결과. 코인 부족 같은 '정상적인 거절'도 200 + ok:false 로 온다
 * (예외로 던지는 건 401/503 뿐이다).
 * coins/owned_items 는 구매 후의 확정 상태라 그대로 덮어쓰면 된다.
 */
export interface BuyItemResponse {
  ok: boolean;
  reason: BuyItemReason;
  coins: number;
  owned_items: string[];
}

export interface CreateRoomBody {
  mode: Mode;
  max_players: number;
  /** 맵 id 또는 'random'. 생략하면 서버 기본 맵. */
  map_id?: string;
}

export interface CreateRoomResponse {
  code: string;
  mode: Mode;
  max_players: number;
  map_id: string;
}

export interface RoomSummary {
  code: string;
  mode: Mode;
  max_players: number;
  player_count: number;
  phase: Phase;
  map_id: string;
}

/** 서버가 내려주는 에러(detail)를 그대로 담는 예외 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      // init.headers 를 통째로 덮어쓰지 않고 병합한다(Authorization 을 얹기 위해).
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다.');
  }

  if (!res.ok) {
    let detail = `요청에 실패했습니다. (${res.status})`;
    try {
      // FastAPI 는 { "detail": "..." } 형태로 에러를 준다.
      const body: unknown = await res.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        const value = (body as { detail: unknown }).detail;
        if (typeof value === 'string') detail = value;
      }
    } catch {
      /* 본문이 JSON 이 아니면 기본 메시지 사용 */
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/api/health');
  },

  createRoom(body: CreateRoomBody): Promise<CreateRoomResponse> {
    return request<CreateRoomResponse>('/api/rooms', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getRoom(code: string): Promise<RoomSummary> {
    return request<RoomSummary>(`/api/rooms/${encodeURIComponent(code)}`);
  },

  getCards(): Promise<CardInfo[]> {
    return request<CardInfo[]>('/api/cards');
  },

  getMaps(): Promise<MapInfo[]> {
    return request<MapInfo[]>('/api/maps');
  },

  // ── 계정 ────────────────────────────────────────────────────────────
  // DB 가 없는 서버에서는 아래 셋 모두 503 을 던진다(ApiError.status === 503).

  /** 익명 계정 발급. 토큰이 없을 때 딱 한 번 부른다. */
  createAnonAccount(body: CreateAnonAccountBody): Promise<CreateAnonAccountResponse> {
    return request<CreateAnonAccountResponse>('/api/auth/anon', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getMe(token: string): Promise<AccountResponse> {
    return request<AccountResponse>('/api/me', { headers: bearer(token) });
  },

  /** 닉네임/아바타만 올린다. 코인은 서버가 정하므로 보내도 무시된다. */
  patchMe(token: string, body: UpdateProfileBody): Promise<AccountResponse> {
    return request<AccountResponse>('/api/me', {
      method: 'PATCH',
      headers: bearer(token),
      body: JSON.stringify(body),
    });
  },

  /**
   * 아이템 구매. 가격은 서버가 정하므로 보내지 않는다 —
   * 클라이언트가 값을 실으면 그게 곧 위조 통로가 된다.
   */
  buyItem(token: string, itemKey: string): Promise<BuyItemResponse> {
    return request<BuyItemResponse>('/api/me/items', {
      method: 'POST',
      headers: bearer(token),
      body: JSON.stringify({ item_key: itemKey }),
    });
  },
};

function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}
