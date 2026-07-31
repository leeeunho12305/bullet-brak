// WebSocket 싱글턴. docs/PROTOCOL.md §2
//
// 60Hz 스냅샷(type:"state")은 React state 로 들어가지 않는다.
// -> net.latest 에 mutable 로만 갱신하고, 렌더러가 rAF 로 읽는다.
// -> store 에는 phase 가 바뀔 때만 반영한다.
import type { ClientMessage, Customization, ServerMessage, Snapshot } from '@/types/game';
import { useGameStore } from '@/store/gameStore';

const WS_BASE =
  import.meta.env.VITE_WS_BASE ||
  (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host;

export interface ConnectProfile {
  nickname: string;
  customization: Customization;
  coins: number;
}

let ws: WebSocket | null = null;
/** store 갱신을 최소화하기 위한 마지막 phase */
let lastPhase: string | null = null;

/** 서버가 지정한 close code -> 한국어 안내 */
function closeMessage(code: number): string | null {
  switch (code) {
    case 4404:
      return '방을 찾을 수 없습니다. 코드를 확인해 주세요.';
    case 4409:
      return '방이 가득 찼습니다.';
    default:
      return null;
  }
}

function parseMessage(raw: string): ServerMessage | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof (parsed as { type?: unknown }).type !== 'string') return null;
    // 서버 계약(PROTOCOL)을 신뢰하고 캐스팅한다.
    return parsed as ServerMessage;
  } catch {
    return null;
  }
}

function handleMessage(msg: ServerMessage): void {
  const store = useGameStore.getState();

  if (msg.type === 'state') {
    // 스냅샷은 mutable 갱신만.
    net.latest = msg as Snapshot;
    if (lastPhase !== msg.phase) {
      lastPhase = msg.phase;
      store.applyServerMessage(msg);
    }
    return;
  }

  if (msg.type === 'welcome' || msg.type === 'room_state') {
    lastPhase = msg.room.phase;
    store.applyServerMessage(msg);
    // 훈련 모드는 대기실 없이 바로 시작한다.
    if (msg.type === 'welcome' && msg.room.mode === 'training' && msg.room.phase === 'waiting') {
      net.send({ type: 'start_game' });
    }
    return;
  }

  store.applyServerMessage(msg);
}

/** 우리가 끊은 경우는 ws 식별자 가드로 걸러지므로 여기 오지 않는다. */
function handleClose(event: CloseEvent): void {
  ws = null;
  net.latest = null;
  lastPhase = null;

  const store = useGameStore.getState();
  const serverError = store.error;
  const mapped = closeMessage(event.code);

  // 정상 종료(1000/1001)면 조용히 로비로 돌아간다.
  if (!mapped && (event.code === 1000 || event.code === 1001) && !serverError) {
    store.reset();
    return;
  }

  const message = mapped ?? serverError ?? '서버와의 연결이 끊어졌습니다.';
  store.reset();
  useGameStore.getState().setStatus('error', message);
}

export const net = {
  /** 최신 스냅샷(React state 아님). 렌더러가 rAF 로 읽는다. */
  latest: null as Snapshot | null,

  /** 미연결이면 조용히 무시 */
  send(msg: ClientMessage): void {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(msg));
  },

  connect(code: string, profile: ConnectProfile): void {
    // 이전 연결이 남아 있으면 정리 (핸들러는 ws 식별자 가드로 무시된다)
    if (ws) {
      const stale = ws;
      ws = null;
      stale.close(1000, 'reconnect');
    }

    net.latest = null;
    lastPhase = null;

    const store = useGameStore.getState();
    store.reset();
    store.setStatus('connecting');

    const url = `${WS_BASE}/ws/${encodeURIComponent(code)}?nickname=${encodeURIComponent(
      profile.nickname,
    )}`;

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      useGameStore.getState().setStatus('error', '서버에 연결할 수 없습니다.');
      return;
    }
    ws = socket;

    socket.onopen = () => {
      if (ws !== socket) return;
      // 접속 직후 join 을 반드시 1회 보낸다.
      net.send({
        type: 'join',
        nickname: profile.nickname,
        customization: profile.customization,
        coins: profile.coins,
      });
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      if (ws !== socket) return;
      if (typeof event.data !== 'string') return;
      const msg = parseMessage(event.data);
      if (msg) handleMessage(msg);
    };

    socket.onerror = () => {
      /* close 핸들러에서 일괄 처리 */
    };

    socket.onclose = (event: CloseEvent) => {
      if (ws !== socket) return;
      handleClose(event);
    };
  },

  disconnect(): void {
    net.latest = null;
    lastPhase = null;
    if (!ws) return;
    const socket = ws;
    ws = null; // 먼저 비워서 onclose 가 에러로 처리하지 않게 한다.
    try {
      socket.close(1000, 'client leave');
    } catch {
      /* 이미 닫힌 경우 무시 */
    }
  },

  isOpen(): boolean {
    return !!ws && ws.readyState === WebSocket.OPEN;
  },
};
