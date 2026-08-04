// docs/PROTOCOL.md 와 1:1 대응. 서버가 보내는 snake_case 를 그대로 쓴다.

export const WORLD_WIDTH = 800;
export const WORLD_HEIGHT = 600;
export const MAX_CHARGE = 60;

export type Phase = 'waiting' | 'playing' | 'round_over' | 'picking' | 'finished';
export type Mode = 'pvp' | 'training';

export interface Customization {
  eye: number;
  mouth: number;
  detail: number;
  color: string;
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

export interface RoomState {
  code: string;
  mode: Mode;
  max_players: number;
  phase: Phase;
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
  block_meter_max: number;
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
  block_meter: number;
  block_meter_max: number;
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

export interface ZoneSnap {
  type: string;
  x: number;
  y: number;
  radius: number;
}

export interface Platform {
  x: number;
  y: number;
  width: number;
  height: number;
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
  players: PlayerSnap[];
  bots: BotSnap[];
  bullets: BulletSnap[];
  zones: ZoneSnap[];
  platforms: Platform[];
  loser_to_pick: string | null;
  available_cards: CardInfo[];
  winner_id: string | null;
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
  | { type: 'welcome'; player_id: string; room: RoomState }
  | { type: 'room_state'; room: RoomState }
  | ({ type: 'state' } & Snapshot)
  | { type: 'chat'; message: ChatMessage }
  | {
      type: 'event';
      event: 'round_over' | 'match_over' | 'card_phase' | 'game_started';
      winner_id: string | null;
      loser_id: string | null;
    }
  | { type: 'error'; message: string };

export type ClientMessage =
  | { type: 'join'; nickname: string; customization: Customization; coins: number }
  | ({ type: 'input' } & InputState)
  | { type: 'aim'; x: number; y: number }
  | { type: 'shoot' }
  | { type: 'strong_start' }
  | { type: 'strong_release' }
  | { type: 'pick_card'; card_id: string }
  | { type: 'chat'; text: string }
  | { type: 'start_game' }
  | { type: 'restart' }
  | { type: 'avatar'; customization: Customization };
