// 라운드 패자가 카드 5장 중 1장을 고르는 오버레이(ROUNDS 의 카드 화면 역할).
// 60Hz 스냅샷을 React state 로 흘리지 않으려고 net.latest 를 저빈도로 샘플링한다.
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { CardInfo, Phase } from '@/types/game';

const SAMPLE_MS = 150;

const CATEGORY_LABEL: Record<string, string> = {
  attack: '공격',
  survival: '생존',
  utility: '유틸',
  movement: '이동',
  special: '특수',
};

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

function CardPickerInner(): JSX.Element | null {
  const myId = useGameStore((s: StoreSlice) => s.playerId);
  const storePhase = useGameStore((s: StoreSlice) => s.phase);
  const [state, setState] = useState<PickState>(EMPTY);
  const [picked, setPicked] = useState<string | null>(null);
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
      if (!next.active) setPicked(null);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [myId, storePhase]);

  const pick = useCallback(
    (cardId: string) => {
      if (picked !== null) return;
      setPicked(cardId);
      if (net.isOpen()) net.send({ type: 'pick_card', card_id: cardId });
    },
    [picked],
  );

  // 숫자키로도 고를 수 있게 (1~5). 마우스를 안 놓쳐도 되니 훨씬 빠르다.
  const canUseKeys = state.active && state.mine && picked === null;
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

  if (!state.mine) {
    return (
      <div className="overlay picking">
        <p className="overlay-kicker">CARD PHASE</p>
        <h2 className="overlay-title">카드 선택</h2>
        <p className="overlay-desc">
          <strong>{state.pickerName}</strong> 님이 고르는 중
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

  return (
    <div className="overlay picking">
      <p className="overlay-kicker">CARD PHASE</p>
      <h2 className="overlay-title">카드를 고르세요</h2>
      <p className="overlay-desc">
        진 쪽에게 주어지는 보상입니다. 하나만 고를 수 있어요 —{' '}
        <kbd>1</kbd>~<kbd>{state.cards.length}</kbd> 키로도 선택됩니다.
      </p>
      {/* locked: 이미 고른 뒤에는 뒤집기를 멈춘다(고른 카드가 계속 보여야 한다) */}
      <div className={`card-row${picked !== null ? ' locked' : ''}`}>
        {state.cards.map((card, i) => {
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
              onClick={() => pick(card.id)}
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
      {picked !== null && <p className="overlay-desc">선택 완료! 다음 라운드를 준비 중…</p>}
    </div>
  );
}

export const CardPicker = memo(CardPickerInner);
export default CardPicker;
