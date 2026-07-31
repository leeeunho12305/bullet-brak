// 라운드 패자가 카드 5장 중 1장을 고르는 오버레이.
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
  cards: CardInfo[];
}

const EMPTY: PickState = { active: false, mine: false, cards: [] };

function signature(s: PickState): string {
  return `${s.active ? 1 : 0}${s.mine ? 1 : 0}${s.cards.map((c) => c.id).join(',')}`;
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
      const next: PickState =
        phase === 'picking' && snap
          ? { active: true, mine: snap.loser_to_pick === myId, cards: snap.available_cards }
          : EMPTY;
      const sig = signature(next);
      if (sig === sigRef.current) return;
      sigRef.current = sig;
      setState(next);
      if (!next.active) setPicked(null);
    }, SAMPLE_MS);
    return () => window.clearInterval(timer);
  }, [myId, storePhase]);

  const pick = useCallback((cardId: string) => {
    setPicked(cardId);
    if (net.isOpen()) net.send({ type: 'pick_card', card_id: cardId });
  }, []);

  if (!state.active) return null;

  if (!state.mine) {
    return (
      <div className="overlay picking">
        <h2 className="overlay-title">카드 선택</h2>
        <p className="overlay-desc">상대가 카드를 고르는 중…</p>
      </div>
    );
  }

  return (
    <div className="overlay picking">
      <h2 className="overlay-title">카드를 고르세요</h2>
      <p className="overlay-desc">패자에게 주어지는 보상입니다. 하나만 선택할 수 있어요.</p>
      <div className="card-row">
        {state.cards.map((card, i) => {
          const disabled = picked !== null;
          return (
            <button
              type="button"
              key={card.id}
              className={`card-item${picked === card.id ? ' picked' : ''}`}
              style={{
                borderColor: card.color,
                boxShadow: `0 0 24px ${card.color}44`,
                animationDelay: `${i * 60}ms`,
              }}
              disabled={disabled}
              onClick={() => pick(card.id)}
            >
              <span className="card-category" style={{ color: card.color }}>
                {CATEGORY_LABEL[card.category] ?? card.category}
              </span>
              <span className="card-emoji">{card.emoji || '🃏'}</span>
              <span className="card-name">{card.name}</span>
              <span className="card-desc">{card.desc}</span>
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
