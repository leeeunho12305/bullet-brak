// 로비 튜토리얼. 처음 들어온 사람이 규칙을 한 번에 훑을 수 있게 단계별로 보여준다.
// 게임 규칙의 실제 수치(ROUNDS_TO_SCORE 등)는 types/game.ts 의 상수를 그대로 쓴다.
import { useCallback, useEffect, useState } from 'react';
import type { JSX, ReactNode } from 'react';
import ControlsGuide from '@/components/ControlsGuide';
import { MAX_PART_PRICE, MIN_PAID_PRICE } from '@/game/avatars';
import { BLOCK_INFO, BLOCK_TYPES, COINS_MATCH_WIN, COINS_ROUND_WIN, ROUNDS_TO_SCORE } from '@/types/game';

interface Step {
  title: string;
  emoji: string;
  body: ReactNode;
}

const STEPS: Step[] = [
  {
    title: '목표',
    emoji: '🏆',
    body: (
      <>
        <p>
          마지막까지 살아남으면 라운드 승리입니다. <strong>{ROUNDS_TO_SCORE}라운드를 이기면 1점</strong>,
          먼저 <strong>5점</strong>을 채우면 매치에서 이깁니다.
        </p>
        <p className="hint">
          체력은 라운드마다 가득 채워집니다. 한 방에 죽지 않으니 맞더라도 자리를 잡는 게 먼저예요.
        </p>
      </>
    ),
  },
  {
    title: '조작',
    emoji: '🎮',
    body: (
      <>
        <ControlsGuide title="" />
        <p className="hint">조작법은 로비 &quot;조작법&quot; 칸에서 언제든 다시 볼 수 있어요.</p>
      </>
    ),
  },
  {
    title: '싸우는 법',
    emoji: '🔫',
    body: (
      <>
        <ul className="tut-list">
          <li>
            <strong>사격</strong> — 좌클릭. 총알은 <em>멀수록 약해집니다</em>. 붙어서 쏘면 훨씬 아파요.
          </li>
          <li>
            <strong>강공격</strong> — 좌클릭을 꾹 눌러 링을 채운 뒤 놓습니다. 세지만 쿨타임이 깁니다.
          </li>
          <li>
            <strong>가드</strong> — 우클릭을 누르고 있는 동안 조준 방향으로 방패가 펼쳐지고, 그동안
            날아온 탄을 그대로 튕겨냅니다. 가드 게이지는 <strong>라운드마다 150</strong>이고 계속
            누르고 있으면 <strong>30초</strong>에 다 닳습니다. 손을 떼면 그 자리에서 멈추니 필요한
            순간에만 짧게 끊어 쓰세요. 카드에 따라 가드하는 순간 장판·반격탄이 나가기도 합니다.
          </li>
          <li>
            <strong>낙사</strong> — 화면 아래로 떨어지면 즉사입니다. 협곡·부유섬에서는 이게 제일 무서워요.
          </li>
        </ul>
      </>
    ),
  },
  {
    title: '카드',
    emoji: '🃏',
    body: (
      <>
        <p>
          라운드에서 <strong>진 사람만</strong> 카드를 한 장 고릅니다. 카드는 매치가 끝날 때까지 계속
          쌓이므로, 지고 있어도 판을 뒤집을 수 있습니다.
        </p>
        <p className="hint">
          Tab 을 누르고 있으면 지금까지 모은 카드와 거리별 대미지 표를 볼 수 있어요.
        </p>
      </>
    ),
  },
  {
    title: '지형과 블럭',
    emoji: '🧱',
    body: (
      <>
        <p>맵마다 발판 종류가 다릅니다. 대기실의 &quot;맵 에디터&quot;로 직접 배치할 수도 있어요.</p>
        <ul className="tut-blocks">
          {BLOCK_TYPES.map((t) => (
            <li key={t}>
              <span className="tut-block-chip" style={{ background: BLOCK_INFO[t].color }} aria-hidden />
              <span>
                <strong>
                  {BLOCK_INFO[t].emoji} {BLOCK_INFO[t].name}
                </strong>{' '}
                — {BLOCK_INFO[t].desc}
              </span>
            </li>
          ))}
        </ul>
      </>
    ),
  },
  {
    title: '코인 모으기',
    emoji: '💰',
    body: (
      <>
        <p>
          코인은 <strong>친구와 하는 대전(방 만들기·참가)</strong>에서만 나옵니다. 이긴 만큼 쌓여요.
        </p>
        <ul className="tut-list">
          <li>
            <strong>라운드 승리</strong> — <strong>+{COINS_ROUND_WIN} 코인</strong>. 한 라운드 이길 때마다
            바로 들어옵니다.
          </li>
          <li>
            <strong>매치 승리</strong> — 먼저 5점을 채워 매치를 끝내면 <strong>+{COINS_MATCH_WIN} 코인</strong>{' '}
            보너스.
          </li>
          <li>
            <strong>훈련장은 코인이 나오지 않습니다.</strong> 봇 웨이브는 연습용이에요.
          </li>
        </ul>
        <p>
          모은 코인은 로비 <strong>아바타 꾸미기</strong>에서 파츠를 사는 데 씁니다(유료 파츠{' '}
          {MIN_PAID_PRICE}~{MAX_PART_PRICE} 코인). 한 번 산 파츠는 계속 남습니다.
        </p>
        <p className="hint">지금 잔액은 로비 위쪽 💰 배지에서 볼 수 있어요.</p>
      </>
    ),
  },
  {
    title: '시작하기',
    emoji: '🚀',
    body: (
      <>
        <ul className="tut-list">
          <li>
            <strong>훈련장</strong> — 혼자서 봇 웨이브를 상대합니다. 조작과 카드를 익히기 좋아요.
          </li>
          <li>
            <strong>방 만들기</strong> — 6자리 코드를 친구에게 알려주면 됩니다.
          </li>
          <li>
            대기실에서 방장이 <strong>맵</strong>을 고르고, <strong>맵 에디터</strong>로 지형을 통째로
            새로 그릴 수 있습니다(원래 블럭도 지워집니다).
          </li>
        </ul>
        <p className="hint">준비됐다면 훈련장부터 한 판 돌려 보세요.</p>
      </>
    ),
  },
];

interface Props {
  onClose(): void;
}

export default function Tutorial({ onClose }: Props): JSX.Element {
  const [index, setIndex] = useState(0);
  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  const go = useCallback((delta: number) => {
    setIndex((i) => Math.max(0, Math.min(STEPS.length - 1, i + delta)));
  }, []);

  // Esc 로 닫고, 좌우 화살표로 넘긴다.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, onClose]);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="튜토리얼">
      <div className="modal tut">
        <header className="modal-head">
          <h2>
            <span aria-hidden>{step.emoji}</span> {step.title}
          </h2>
          <button type="button" className="btn btn-ghost modal-x" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </header>

        <div className="modal-body tut-body">{step.body}</div>

        <footer className="modal-foot">
          <div className="tut-dots" aria-hidden>
            {STEPS.map((s, i) => (
              <span key={s.title} className={i === index ? 'tut-dot is-on' : 'tut-dot'} />
            ))}
          </div>
          <div className="row">
            <button type="button" className="btn btn-ghost" disabled={index === 0} onClick={() => go(-1)}>
              이전
            </button>
            {last ? (
              <button type="button" className="btn btn-primary" onClick={onClose}>
                시작하기
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => go(1)}>
                다음 ({index + 1}/{STEPS.length})
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
