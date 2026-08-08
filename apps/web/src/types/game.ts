// docs/PROTOCOL.md 와 1:1 대응. 서버가 보내는 snake_case 를 그대로 쓴다.

export const WORLD_WIDTH = 800;
export const WORLD_HEIGHT = 600;
export const MAX_CHARGE = 60;
/** 라운드 2승 = 1점 (서버 constants.ROUNDS_TO_SCORE 와 같아야 한다) */
export const ROUNDS_TO_SCORE = 2;
/** 라운드 승리 보상 (서버 constants.COINS_ROUND_WIN) */
export const COINS_ROUND_WIN = 10;
/** 매치 승리 보상 (서버 constants.COINS_MATCH_WIN) */
export const COINS_MATCH_WIN = 100;

export type Phase = 'waiting' | 'playing' | 'round_over' | 'picking' | 'finished';
export type Mode = 'pvp' | 'training';

/** 편집기 탭 = 파츠 슬롯 (EYES · MOUTHS · DETAIL1 · DETAIL2) */
export type PartSlot = 'eye' | 'mouth' | 'detail' | 'detail2';

/** 파츠를 몸통 박스 대비 비율만큼 밀어 놓은 값. 편집기에서 드래그로 정한다. */
export interface PartOffset {
  x: number;
  y: number;
}

export type PartOffsets = Partial<Record<PartSlot, PartOffset>>;

export interface Customization {
  eye: number;
  mouth: number;
  detail: number;
  detail2: number;
  color: string;
  /** 슬롯별 위치 보정. 없으면 전부 0. */
  offsets?: PartOffsets;
}

export interface Vec {
  x: number;
  y: number;
}

export interface RoomPlayer {
  id: string;
  nickname: string;
  customization: Customization;
  coins: number;
}

/** 맵 배경/발판 색. renderer 가 그대로 받아 쓴다. */
export interface MapTheme {
  bg: string;
  grid: string;
  platform: string;
  edge: string;
}

/** 맵 카탈로그 한 칸 (GET /api/maps · RoomState.map) */
export interface MapInfo {
  id: string;
  name: string;
  emoji: string;
  desc: string;
  theme: MapTheme;
  platforms: Platform[];
  spawns: Vec[];
}

/** 방장이 "무작위"를 골랐을 때의 값. 실제 맵 id 가 아니다. */
export const RANDOM_MAP_ID = 'random';

export interface RoomState {
  code: string;
  mode: Mode;
  max_players: number;
  phase: Phase;
  /** 방장이 고른 값. 'random' 일 수 있다. */
  map_id: string;
  /** 지금 실제로 깔려 있는 맵. platforms 는 에디터로 고친 결과가 반영된 값이다. */
  map: MapInfo;
  /** 발판이 맵 원본이 아니라 방장이 맵 에디터로 짠 배치인가 */
  custom_map: boolean;
  players: RoomPlayer[];
}

export interface PlayerStats {
  damage_mult: number;
  max_hp: number;
  speed: number;
  cooldown: number;
  bullet_speed: number;
  bullet_size: number;
  bounces: number;
  knockback: number;
  /** 라운드당 쓸 수 있는 가드 횟수 */
  block_uses: number;
  /** 가드 한 번이 펼쳐져 있는 시간(초) */
  block_seconds: number;
  shots_per_fire: number;
}

export interface DamageRow {
  distance: number;
  damage: number;
}

export interface PlayerSnap {
  id: string;
  nickname: string;
  customization: Customization;
  x: number;
  y: number;
  width: number;
  height: number;
  vx: number;
  vy: number;
  hp: number;
  max_hp: number;
  alive: boolean;
  aim: Vec;
  cooldown: number;
  max_cooldown: number;
  /** 이번 라운드에 남은 가드 횟수. 게이지가 아니라서 라운드 안에서는 다시 차지 않는다. */
  block_uses: number;
  block_uses_max: number;
  /** 가드가 펼쳐져 있는 남은 틱(0이면 가드 중이 아니다) */
  block_timer: number;
  /** 가드 한 번이 유지되는 틱 */
  block_duration: number;
  blocking: boolean;
  charging: boolean;
  charge: number;
  score: number;
  round_wins: number;
  coins: number;
  cards: string[];
  silenced: boolean;
  poison: number;
  cold: boolean;
  /** 0.5초에 한 번만 실린다(대역폭 절약). 없으면 마지막으로 받은 값을 유지한다. */
  stats?: PlayerStats;
  damage_table?: DamageRow[];
}

/** 훈련장 봇 난이도 (PROTOCOL §3 BotSnap.tier) */
export type BotTier = 'dummy' | 'rookie' | 'veteran';

export interface BotSnap {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  hp: number;
  max_hp: number;
  customization: Customization;
  tier: BotTier;
  /** 봇이 겨누는 지점. 허수아비는 자기 위치라 시선이 안 그려진다. */
  aim: Vec;
}

export interface BulletSnap {
  id: number;
  x: number;
  y: number;
  size: number;
  owner: string;
  color: string;
}

/** 폭발 섬광(zone type 'blast')이 남아 있는 틱. 서버 constants.BLAST_TICKS 와 같아야 한다. */
export const BLAST_TICKS = 12;

export interface ZoneSnap {
  /** heal|toxic|static|emp|frost|implode|shockwave|radiance|chilling|blast */
  type: string;
  x: number;
  y: number;
  radius: number;
  /** 남은 틱. blast 는 이 값으로 퍼지는 정도를 그린다. */
  d: number;
}

/**
 * 발판 종류 (서버 game/blocks.py 의 TYPES 와 같은 값이어야 한다).
 *  solid  일반 블럭 · jump 점프대 · mover 이동발판 · ice 빙판 · hazard 가시
 */
export type BlockType = 'solid' | 'jump' | 'mover' | 'ice' | 'hazard';

export const BLOCK_TYPES: BlockType[] = ['solid', 'jump', 'mover', 'ice', 'hazard'];

/** 팔레트/범례용 표시 정보. 색은 renderer 와 MapPreview 가 공유한다. */
export const BLOCK_INFO: Record<BlockType, { name: string; emoji: string; color: string; desc: string }> = {
  solid: { name: '일반 블럭', emoji: '⬛', color: '#8d99ae', desc: '평범한 발판. 위아래·옆 모두 막힌다.' },
  jump: {
    name: '점프대',
    emoji: '🔼',
    color: '#51cf66',
    desc: '바닥에 박아 넣는 발판. 걸려 넘어지지 않고 지나가면 그대로 튀어오른다.',
  },
  mover: { name: '이동 발판', emoji: '↔️', color: '#4dabf7', desc: '정해진 구간을 왕복한다. 올라타면 같이 실려 간다.' },
  ice: { name: '빙판', emoji: '🧊', color: '#99e9f2', desc: '마찰이 거의 없다. 멈추기 어렵다.' },
  hazard: { name: '가시', emoji: '🔺', color: '#ff6b6b', desc: '한 번 밟을 때마다 50 피해를 입고 튕겨난다.' },
};

export interface Platform {
  x: number;
  y: number;
  width: number;
  height: number;
  /** 없으면 'solid' (서버가 일반 블럭에서는 생략한다) */
  type?: BlockType;
  /** 점프대 위력(위로 향하는 속도) */
  power?: number;
  /** 이동발판이 왕복하는 축 */
  axis?: 'x' | 'y';
  /** 이동발판 왕복 폭 / 속도 — 에디터에서만 쓰고 스냅샷에는 실리지 않는다. */
  span?: number;
  speed?: number;
}

export interface CardInfo {
  id: string;
  name: string;
  desc: string;
  category: 'attack' | 'survival' | 'utility' | 'movement' | 'special';
  color: string;
  emoji: string;
}

export interface ChatMessage {
  sender: string;
  text: string;
  time: number;
}

export interface Snapshot {
  type: 'state';
  tick: number;
  phase: Phase;
  mode: Mode;
  /** 지금 깔려 있는 맵 id. 이름/테마는 room_state 로만 온다(대역폭). */
  map_id: string;
  players: PlayerSnap[];
  bots: BotSnap[];
  bullets: BulletSnap[];
  zones: ZoneSnap[];
  /**
   * 지금 깔린 발판. 서버는 LAYOUT_INTERVAL(0.5초)마다만 전부 실어 보낸다 —
   * connection.ts 가 직전 목록을 기억했다가 채워 넣으므로 렌더러에서는 항상 채워져 있다.
   */
  platforms: Platform[];
  /** 그 사이 틱의 이동발판 좌표만. i 는 platforms 의 인덱스다. */
  movers?: { i: number; x: number; y: number }[];
  loser_to_pick: string | null;
  available_cards: CardInfo[];
  winner_id: string | null;
  /** 리매치에 동의한 플레이어 id. finished 에서만 찬다. */
  rematch: string[];
  /** 훈련장 진행 상황. pvp 방이면 null (PROTOCOL §3 TrainingSnap) */
  training: TrainingSnap | null;
}

export type TrainingPhase = 'fighting' | 'wave_clear' | 'respawning';

export interface TrainingSnap {
  wave: number;
  bots_left: number;
  wave_bots: number;
  state: TrainingPhase;
  /** 다음 전환까지 남은 틱(0이면 카운트다운 없음) */
  timer: number;
  kills: number;
  deaths: number;
  best_wave: number;
  shots: number;
  hits: number;
  damage_dealt: number;
  damage_taken: number;
  survived_ticks: number;
}

export interface InputState {
  left: boolean;
  right: boolean;
  jump: boolean;
  block: boolean;
}

export type ServerMessage =
  | {
      type: 'welcome';
      player_id: string;
      room: RoomState;
      /** 이번 입장이 계정에 묶였는지. null 이면 비로그인(진행이 저장되지 않는다). */
      account_id?: string | null;
    }
  | { type: 'room_state'; room: RoomState }
  | ({ type: 'state' } & Snapshot)
  | { type: 'chat'; message: ChatMessage }
  | {
      type: 'event';
      event: 'round_over' | 'match_over' | 'card_phase' | 'game_started';
      winner_id: string | null;
      loser_id: string | null;
    }
  /** 누군가 방을 나갔다. 남아 있는 사람에게만 온다(나간 본인은 이미 연결이 끊겼다). */
  | { type: 'player_left'; player_id: string; nickname: string; players_left: number }
  | { type: 'error'; message: string };

export type ClientMessage =
  | {
      type: 'join';
      nickname: string;
      customization: Customization;
      /** 비로그인일 때만 쓰인다. 토큰이 유효하면 서버가 계정 잔액으로 덮는다. */
      coins: number;
      /** 디바이스 토큰. 없으면 비로그인으로 입장한다. */
      token?: string;
    }
  | ({ type: 'input' } & InputState)
  | { type: 'aim'; x: number; y: number }
  | { type: 'shoot' }
  | { type: 'strong_start' }
  | { type: 'strong_release' }
  | { type: 'pick_card'; card_id: string }
  | { type: 'chat'; text: string }
  | { type: 'start_game' }
  | { type: 'restart' }
  | { type: 'rematch'; accept: boolean }
  | { type: 'avatar'; customization: Customization }
  /** 방장 전용. 서버가 방장이 아닌 요청은 조용히 무시한다. */
  | { type: 'set_map'; map_id: string }
  /** 방장 전용. 맵 에디터로 짠 배치를 저장한다(대기실에서만 유효). */
  | { type: 'set_platforms'; platforms: Platform[] }
  /** 방장 전용. 맵 원본 지형으로 되돌린다. */
  | { type: 'reset_platforms' };
