// 라운드 패자가 카드 5장 중 1장을 고르는 오버레이(ROUNDS 의 카드 화면 역할).
// 훈련장에서는 서버가 카드를 전부 열어 주므로(engine.open_card_pick) 5장짜리 뒤집기 대신
// 검색·분류가 되는 목록으로 그린다 — 68장을 뒤집어 가며 찾게 할 수는 없다.
// 60Hz 스냅샷을 React state 로 흘리지 않으려고 net.latest 를 저빈도로 샘플링한다.
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { CardInfo, Phase } from '@/types/game';

const SAMPLE_MS = 150;

/** 이보다 많이 열리면 뒤집기 카드가 아니라 목록으로 그린다(= 훈련장). */
const BROWSE_THRESHOLD = 8;

const CATEGORY_LABEL: Record<string, string> = {
  attack: '공격',
  survival: '생존',
  utility: '유틸',
  movement: '이동',
  special: '특수',
};

const CATEGORY_ORDER = ['attack', 'survival', 'utility', 'movement', 'special'];

interface StoreSlice {
  playerId: string | null;
  phase: Phase;
}

interface PickState {
  active: boolean;
  mine: boolean;
  /** 카드를 고르는 사람의 닉네임(내 차례가 아닐 때 보여준다) */
  pickerName: string;
  cards: CardInfo[];
}

const EMPTY: PickState = { active: false, mine: false, pickerName: '', cards: [] };

function signature(s: PickState): string {
  return `${s.active ? 1 : 0}${s.mine ? 1 : 0}${s.pickerName}|${s.cards.map((c) => c.id).join(',')}`;
}

function usePickState(myId: string | null, storePhase: Phase): PickState {
  const [state, setState] = useState<PickState>(EMPTY);
  const sigRef = useRef<string>(signature(EMPTY));

  useEffect(() => {
    const timer = window.setInterval(() => {
      const snap = net.latest;
      const phase = snap ? snap.phase : storePhase;
      let next = EMPTY;
      if (phase === 'picking' && snap) {
        const picker = snap.players.find((p) => p.id === snap.loser_to_pick);
        next = {
          active: true,
          mine: snap.loser_to_pick === myId,
          pickerName: picker?.nickname || '상대',
          cards: snap.available_cards,
        };
      }
      const sig = signature(next);
      if (sig === sigRef.current) return;
      sigRef.current = sig;
      setState(next);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [myId, storePhase]);

  return state;
}

/** 상대가 고르는 동안 보여주는 뒷면 다섯 장 */
function WaitingRow({ name }: { name: string }): JSX.Element {
  return (
    <div className="overlay picking">
      <p className="overlay-kicker">CARD PHASE</p>
      <h2 className="overlay-title">카드 선택</h2>
      <p className="overlay-desc">
        <strong>{name}</strong> 님이 고르는 중
        <span className="dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </p>
      <div className="card-row">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className="card-back" style={{ animationDelay: `${i * 90}ms` }}>
            ?
          </span>
        ))}
      </div>
    </div>
  );
}

interface DeckProps {
  cards: CardInfo[];
  picked: string | null;
  onPick: (id: string) => void;
}

/** 대전용 — 다섯 장을 엎어 두고 가리킨 한 장만 뒤집는다. */
function FlipRow({ cards, picked, onPick }: DeckProps): JSX.Element {
  return (
    /* locked: 이미 고른 뒤에는 뒤집기를 멈춘다(고른 카드가 계속 보여야 한다) */
    <div className={`card-row${picked !== null ? ' locked' : ''}`}>
      {cards.map((card, i) => {
        const isPicked = picked === card.id;
        return (
          <button
            type="button"
            key={card.id}
            className={`card-item${isPicked ? ' picked' : ''}${
              picked !== null && !isPicked ? ' faded' : ''
            }`}
            style={{ animationDelay: `${i * 60}ms` }}
            disabled={picked !== null}
            aria-label={`${card.name} — ${card.desc}`}
            onClick={() => onPick(card.id)}
          >
            <span className="card-inner">
              <span
                className="card-face card-front"
                style={{
                  borderColor: card.color,
                  boxShadow: `0 0 24px ${card.color}44`,
                  // 카드 색을 배경 그라데이션에도 섞어 카테고리가 한눈에 구분되게 한다.
                  background: `linear-gradient(165deg, ${card.color}22, var(--panel) 62%)`,
                }}
              >
                <span className="card-key" aria-hidden>
                  {i + 1}
                </span>
                <span className="card-stripe" style={{ background: card.color }} />
                <span className="card-category" style={{ color: card.color }}>
                  {CATEGORY_LABEL[card.category] ?? card.category}
                </span>
                <span className="card-emoji">{card.emoji || '🃏'}</span>
                <span className="card-name">{card.name}</span>
                <span className="card-desc">{card.desc}</span>
              </span>
              {/* 뒷면 — 기본 상태. 마우스를 올린 카드만 앞면으로 돌아온다.
                  번호를 여기에도 박아 둬야 다 엎어진 상태에서 1~5 키를 쓸 수 있다. */}
              <span
                className="card-face card-rear"
                style={{ borderColor: `${card.color}55` }}
                aria-hidden
              >
                <span className="card-key">{i + 1}</span>
                <span className="card-rear-mark">?</span>
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * 훈련장용 — 전부 앞면으로 펼쳐 놓고 검색/분류로 좁힌다.
 * 여기서는 "운"이 아니라 "무엇을 시험해 볼지"가 요점이라 엎어 둘 이유가 없다.
 */
function BrowseGrid({ cards, picked, onPick }: DeckProps): JSX.Element {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string>('all');

  const categories = useMemo(() => {
    const found = new Set(cards.map((c) => c.category));
    return CATEGORY_ORDER.filter((c) => found.has(c as CardInfo['category']));
  }, [cards]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cards.filter((c) => {
      if (category !== 'all' && c.category !== category) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.desc.toLowerCase().includes(q) ||
        c.id.includes(q)
      );
    });
  }, [cards, query, category]);

  return (
    <>
      <div className="card-filter">
        <input
          type="search"
          className="card-search"
          placeholder="카드 이름이나 설명으로 검색"
          value={query}
          disabled={picked !== null}
          // 여기에 포커스가 있는 동안 이동 키가 게임으로 새지 않는 건 useInput 이 막는다
          // (INPUT/TEXTAREA/SELECT 에 포커스가 있으면 입력을 읽지 않는다).
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="card-chips">
          <button
            type="button"
            className={`card-chip${category === 'all' ? ' on' : ''}`}
            onClick={() => setCategory('all')}
          >
            전체 {cards.length}
          </button>
          {categories.map((c) => (
            <button
              type="button"
              key={c}
              className={`card-chip${category === c ? ' on' : ''}`}
              onClick={() => setCategory(c)}
            >
              {CATEGORY_LABEL[c] ?? c}
            </button>
          ))}
        </div>
      </div>
      <div className="card-grid">
        {shown.map((card) => {
          const isPicked = picked === card.id;
          return (
            <button
              type="button"
              key={card.id}
              className={`card-tile${isPicked ? ' picked' : ''}${
                picked !== null && !isPicked ? ' faded' : ''
              }`}
              style={{
                borderColor: card.color,
                background: `linear-gradient(160deg, ${card.color}1f, var(--panel) 70%)`,
              }}
              disabled={picked !== null}
              aria-label={`${card.name} — ${card.desc}`}
              onClick={() => onPick(card.id)}
            >
              <span className="card-tile-head">
                <span className="card-emoji">{card.emoji || '🃏'}</span>
                <span className="card-name">{card.name}</span>
                <span className="card-category" style={{ color: card.color }}>
                  {CATEGORY_LABEL[card.category] ?? card.category}
                </span>
              </span>
              <span className="card-desc">{card.desc}</span>
            </button>
          );
        })}
        {shown.length === 0 && <p className="info-empty">검색과 맞는 카드가 없습니다</p>}
      </div>
    </>
  );
}

function CardPickerInner(): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const state = usePickState(myId, storePhase);
  const [picked, setPicked] = useState<string | null>(null);

  // 카드 창이 닫히면 다음 번을 위해 선택을 비운다.
  useEffect(() => {
    if (!state.active) setPicked(null);
  }, [state.active]);

  const pick = useCallback(
    (cardId: string) => {
      if (picked !== null) return;
      setPicked(cardId);
      if (net.isOpen()) net.send({ type: 'pick_card', card_id: cardId });
    },
    [picked],
  );

  const browse = state.cards.length > BROWSE_THRESHOLD;

  // 숫자키로도 고를 수 있게 (1~5). 마우스를 안 놓쳐도 되니 훨씬 빠르다.
  // 목록 화면(훈련장)에서는 번호가 붙지 않으므로 켜지 않는다 — 검색창 입력과도 부딪힌다.
  const canUseKeys = state.active && state.mine && picked === null && !browse;
  useEffect(() => {
    if (!canUseKeys) return;
    const onKey = (e: KeyboardEvent): void => {
      const index = Number(e.key) - 1;
      if (!Number.isInteger(index) || index < 0 || index >= state.cards.length) return;
      e.preventDefault();
      pick(state.cards[index].id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canUseKeys, state.cards, pick]);

  if (!state.active) return null;
  if (!state.mine) return <WaitingRow name={state.pickerName} />;

  return (
    <div className={`overlay picking${browse ? ' browsing' : ''}`}>
      <p className="overlay-kicker">CARD PHASE</p>
      <h2 className="overlay-title">카드를 고르세요</h2>
      <p className="overlay-desc">
        {browse ? (
          <>훈련장에서는 <strong>모든 카드</strong>를 고를 수 있습니다 — 마음껏 시험해 보세요.</>
        ) : (
          <>
            진 쪽에게 주어지는 보상입니다. 하나만 고를 수 있어요 — <kbd>1</kbd>~
            <kbd>{state.cards.length}</kbd> 키로도 선택됩니다.
          </>
        )}
      </p>
      {browse ? (
        <BrowseGrid cards={state.cards} picked={picked} onPick={pick} />
      ) : (
        <FlipRow cards={state.cards} picked={picked} onPick={pick} />
      )}
      {picked !== null && <p className="overlay-desc">선택 완료! 곧 이어집니다…</p>}
    </div>
  );
}

export const CardPicker = memo(CardPickerInner);
export default CardPicker;
