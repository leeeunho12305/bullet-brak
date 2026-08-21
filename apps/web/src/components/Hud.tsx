// 인게임 HUD. 60Hz 스냅샷을 ~10Hz 로 샘플링해서 리렌더한다.
import { memo, useEffect, useMemo, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import ScoreOrb from '@/components/ScoreOrb';
import { MAX_CHARGE } from '@/types/game';
import type { CardInfo, PlayerSnap, TrainingSnap } from '@/types/game';

const SAMPLE_MS = 100;
const SCORE_TO_WIN = 5;
/** 서버 틱레이트. 훈련장 카운트다운(틱)을 초로 바꾸는 데만 쓴다. */
const TICK_RATE = 60;

/** 정지 충전(windup)을 쓰는 카드들 — renderer.ts 의 FOCUS_CARDS 와 같은 목록이다. */
const FOCUS_CARDS = new Set(['wind_up', 'careful_planning', 'ritual_countdown']);

/** 카드 아이콘을 보여주기 위해 지나간 available_cards 를 기억해 둔다. */
const cardCache = new Map<string, CardInfo>();

interface StoreSlice {
  playerId: string | null;
}

interface HudPlayer {
  id: string;
  nickname: string;
  color: string;
  hp: number;
  maxHp: number;
  alive: boolean;
  score: number;
  roundWins: number;
  /** 이번 라운드에 남은 가드 게이지 / 최대치 */
  guard: number;
  guardMax: number;
  /** 지금 가드를 펼치고 있는가(게이지가 줄어드는 중) */
  guarding: boolean;
  cooldown: number;
  charge: number;
  charging: boolean;
  cards: string[];
  silenced: boolean;
  poison: number;
  cold: boolean;
  /** 집중 게이지(0~1). 집중 카드가 없으면 null 이라 게이지를 안 그린다. */
  focus: number | null;
}

function toHudPlayer(p: PlayerSnap): HudPlayer {
  return {
    id: p.id,
    nickname: p.nickname || '익명',
    color: p.customization?.color ?? '#ff6b6b',
    hp: Math.max(0, Math.ceil(p.hp)),
    maxHp: Math.max(1, p.max_hp),
    alive: p.alive,
    score: p.score,
    roundWins: p.round_wins,
    guard: Math.max(0, Math.round(p.block_meter)),
    guardMax: Math.max(1, Math.round(p.block_meter_max)),
    guarding: p.blocking,
    cooldown: p.max_cooldown > 0 ? p.cooldown / p.max_cooldown : 0,
    charge: Math.min(1, p.charge / MAX_CHARGE),
    charging: p.charging,
    cards: p.cards,
    silenced: p.silenced,
    poison: p.poison,
    cold: p.cold,
    focus: p.cards.some((c) => FOCUS_CARDS.has(c)) ? Math.min(1, p.windup / MAX_CHARGE) : null,
  };
}

function useHudSample(myId: string | null): HudPlayer[] {
  const [players, setPlayers] = useState<HudPlayer[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      if (!snap) return;
      for (let i = 0; i < snap.available_cards.length; i += 1) {
        const c = snap.available_cards[i];
        if (!cardCache.has(c.id)) cardCache.set(c.id, c);
      }
      const list = snap.players.map(toHudPlayer);
      // 내가 항상 왼쪽에 오도록 정렬한다.
      if (myId) {
        const idx = list.findIndex((p) => p.id === myId);
        if (idx > 0) {
          const [me] = list.splice(idx, 1);
          list.unshift(me);
        }
      }
      setPlayers(list);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [myId]);

  return players;
}

/** 훈련장 상태도 같은 주기로 표본만 뜬다(60Hz 스냅샷을 state 로 넣지 않는다). */
function useTrainingSample(): TrainingSnap | null {
  const [training, setTraining] = useState<TrainingSnap | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setTraining(net.latest?.training ?? null);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, []);

  return training;
}

interface MeterProps {
  ratio: number;
  color: string;
  label?: string;
}

function Meter({ ratio, color, label }: MeterProps): JSX.Element {
  const pct = `${Math.round(Math.max(0, Math.min(1, ratio)) * 100)}%`;
  return (
    <div className="hud-meter" title={label}>
      <span style={{ width: pct, background: color }} />
    </div>
  );
}

interface SideProps {
  p: HudPlayer;
  mine: boolean;
  side: 'left' | 'right';
}

function PlayerSide({ p, mine, side }: SideProps): JSX.Element {
  return (
    <div className={`hud-side ${side}${p.alive ? '' : ' dead'}`}>
      <div className="hud-name">
        <span className="hud-swatch" style={{ background: p.color }} />
        <strong>{p.nickname}</strong>
        {mine && <em className="hud-tag">나</em>}
        {p.silenced && <span title="침묵">🔇</span>}
        {p.poison > 0 && <span title="중독">🧪</span>}
        {p.cold && <span title="빙결">❄️</span>}
      </div>
      <div className="hud-hp">
        <Meter ratio={p.hp / p.maxHp} color={mine ? 'var(--accent-2)' : 'var(--accent)'} label="체력" />
        <span className="hud-hp-text">
          {p.hp}/{Math.round(p.maxHp)}
        </span>
      </div>
      <div className="hud-sub">
        {/* 가드 게이지는 라운드마다 채워지고, 누르고 있는 동안에만 줄어든다.
            남은 양을 눈으로도(막대) 숫자로도 보여 준다. */}
        <div
          className={`hud-guard${p.guarding ? ' is-on' : ''}`}
          title={`가드 ${p.guard}/${p.guardMax} — 라운드마다 채워진다`}
        >
          <Meter ratio={p.guard / p.guardMax} color={p.guarding ? '#00e5ff' : '#4dabf7'} label="가드" />
          <span className="hud-guard-text">
            {p.guard}/{p.guardMax}
          </span>
        </div>
        <Meter ratio={1 - p.cooldown} color="#adb5bd" label="사격 쿨다운" />
        <Meter
          ratio={p.charge}
          color={p.charging ? '#ff2e97' : 'rgba(255,212,59,0.55)'}
          label="강공격 차징"
        />
        {p.focus !== null && (
          <Meter
            ratio={p.focus}
            color={p.focus >= 1 ? '#c0eb75' : 'rgba(192,235,117,0.6)'}
            label={p.focus >= 1 ? '집중 완료' : '집중 게이지'}
          />
        )}
      </div>
      <div className="hud-bottom">
        <ScoreOrb wins={p.roundWins} color={p.color} />
        <div className="hud-cards">
          {p.cards.map((id, i) => {
            const info = cardCache.get(id);
            return (
              <span
                key={`${id}-${i}`}
                className="hud-card"
                title={info ? `${info.name} — ${info.desc}` : id}
                style={info ? { borderColor: info.color } : undefined}
              >
                {info?.emoji ?? '🃏'}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** 훈련장 전용 중앙 패널. 대전의 점수판 자리를 대신한다. */
function TrainingCenter({ t }: { t: TrainingSnap }): JSX.Element {
  const accuracy = t.shots > 0 ? Math.round((t.hits / t.shots) * 100) : 0;
  const seconds = (t.timer / TICK_RATE).toFixed(1);

  let banner: string | null = null;
  if (t.state === 'wave_clear') banner = `웨이브 ${t.wave} 클리어! 카드 선택 ${seconds}초`;
  else if (t.state === 'respawning') banner = `부활까지 ${seconds}초`;

  // 훈련장은 시험해 보는 곳이다 — 웨이브를 깰 때까지 기다리지 않고 아무 때나 카드를 연다.
  // 서버가 mode/phase 를 다시 검사하므로(engine.open_training_cards) 여기서는 힌트만 준다.
  const openCards = (): void => {
    if (net.isOpen()) net.send({ type: 'open_cards' });
  };

  return (
    <div className="hud-score hud-training">
      <span className="hud-score-num">W{t.wave}</span>
      <div className="hud-training-row">
        <span title="남은 봇">🤖 {t.bots_left}/{t.wave_bots}</span>
        <span title="처치">💀 {t.kills}</span>
        <span title="명중률">🎯 {accuracy}%</span>
        <span title="사망">☠ {t.deaths}</span>
      </div>
      <div className="hud-score-hint">{banner ?? `최고 W${t.best_wave}`}</div>
      <button
        type="button"
        className="hud-cards-btn"
        disabled={t.state !== 'fighting'}
        title="훈련장에서는 아무 때나 원하는 카드를 가져올 수 있습니다"
        onClick={openCards}
      >
        🃏 카드 고르기
      </button>
    </div>
  );
}

function HudInner(): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const players = useHudSample(myId);
  const training = useTrainingSample();
  const [left, right] = useMemo(() => [players[0], players[1]], [players]);

  if (!left) return null;

  return (
    <div className="hud-root">
      <PlayerSide p={left} mine={left.id === myId} side="left" />
      {training ? (
        <TrainingCenter t={training} />
      ) : (
        <div className="hud-score">
          <span className="hud-score-num">{left.score}</span>
          <span className="hud-vs">VS</span>
          <span className="hud-score-num">{right ? right.score : 0}</span>
          <div className="hud-score-hint">{SCORE_TO_WIN}점 선취</div>
        </div>
      )}
      {training ? null : right ? (
        <PlayerSide p={right} mine={right.id === myId} side="right" />
      ) : (
        <div className="hud-side right waiting">상대 대기 중…</div>
      )}
    </div>
  );
}

export const Hud = memo(HudInner);
export default Hud;
