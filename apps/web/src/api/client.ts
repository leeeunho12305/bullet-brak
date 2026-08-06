// REST 클라이언트 — docs/PROTOCOL.md §1
import type { CardInfo, MapInfo, Mode, Phase } from '@/types/game';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export interface HealthResponse {
  status: string;
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
      headers: { 'Content-Type': 'application/json' },
      ...init,
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
};
