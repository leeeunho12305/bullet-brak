// 로비: 닉네임 / 외형 / 코인 + 방 만들기 · 코드로 참가 · 훈련 모드
import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import AvatarEditor from '@/components/AvatarEditor';
import { ApiError, api } from '@/api/client';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { useLocalProfile } from '@/hooks/useLocalProfile';

const NICKNAME_MAX = 12;
const CODE_LENGTH = 6;

function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return '알 수 없는 오류가 발생했습니다.';
}

export default function LobbyScreen() {
  const { nickname, customization, coins, setNickname } = useLocalProfile();
  const status = useGameStore((s) => s.status);
  const storeError = useGameStore((s) => s.error);

  const [code, setCode] = useState('');
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const connecting = status === 'connecting' || busy;
  const message = localError ?? storeError;

  const profile = useCallback(
    () => ({
      nickname: nickname.trim() || '익명',
      customization,
      coins,
    }),
    [nickname, customization, coins],
  );

  /** 방 생성 후 곧바로 WS 접속 */
  const openRoom = useCallback(
    async (mode: 'pvp' | 'training') => {
      setLocalError(null);
      setBusy(true);
      try {
        const room = await api.createRoom({
          mode,
          max_players: mode === 'training' ? 1 : maxPlayers,
        });
        net.connect(room.code, profile());
      } catch (e) {
        setLocalError(errorText(e));
      } finally {
        setBusy(false);
      }
    },
    [maxPlayers, profile],
  );

  const joinRoom = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      if (code.length !== CODE_LENGTH) {
        setLocalError(`${CODE_LENGTH}자리 숫자 코드를 입력해 주세요.`);
        return;
      }
      setLocalError(null);
      setBusy(true);
      try {
        // 먼저 방 존재를 확인해 두면 실패 메시지를 바로 보여줄 수 있다.
        await api.getRoom(code);
        net.connect(code, profile());
      } catch (e) {
        setLocalError(e instanceof ApiError && e.status === 404 ? '방을 찾을 수 없습니다.' : errorText(e));
      } finally {
        setBusy(false);
      }
    },
    [code, profile],
  );

  return (
    <div className="screen">
      <header className="brand">
        <h1>BULLET BRAK</h1>
        <span className="badge">💰 {coins}</span>
      </header>

      {message ? (
        <div className="alert" role="alert">
          {message}
        </div>
      ) : null}

      <div className="lobby-grid">
        <section className="panel">
          <h2 className="section-title">플레이어</h2>

          <div className="field">
            <label className="label" htmlFor="nickname">
              닉네임
            </label>
            <input
              id="nickname"
              className="input"
              value={nickname}
              maxLength={NICKNAME_MAX}
              placeholder="익명"
              autoComplete="off"
              onChange={(e) => setNickname(e.target.value.slice(0, NICKNAME_MAX))}
            />
          </div>

          {/* 외형 편집기(동료 컴포넌트) — store 의 customization 을 직접 갱신한다 */}
          <AvatarEditor />
        </section>

        <section className="panel">
          <h2 className="section-title">게임 시작</h2>

          <div className="field">
            <label className="label" htmlFor="maxPlayers">
              방 인원
            </label>
            <select
              id="maxPlayers"
              className="input"
              value={maxPlayers}
              onChange={(e) => setMaxPlayers(Number(e.target.value))}
            >
              <option value={2}>2명</option>
              <option value={3}>3명</option>
              <option value={4}>4명</option>
            </select>
          </div>

          <button
            type="button"
            className="btn btn-primary btn-block"
            disabled={connecting}
            onClick={() => void openRoom('pvp')}
          >
            {connecting ? <span className="spinner" aria-hidden /> : null}
            방 만들기
          </button>

          <div className="divider" />

          <form onSubmit={(e) => void joinRoom(e)}>
            <label className="label" htmlFor="roomCode">
              코드로 참가
            </label>
            <div className="row">
              <input
                id="roomCode"
                className="input code-input"
                value={code}
                inputMode="numeric"
                autoComplete="off"
                placeholder="000000"
                aria-label="방 코드 6자리"
                onChange={(e) =>
                  setCode(e.target.value.toUpperCase().replace(/[^0-9]/g, '').slice(0, CODE_LENGTH))
                }
              />
              <button
                type="submit"
                className="btn"
                disabled={connecting || code.length !== CODE_LENGTH}
              >
                참가
              </button>
            </div>
            <p className="hint">Enter 로 바로 참가할 수 있어요.</p>
          </form>

          <div className="divider" />

          <button
            type="button"
            className="btn btn-ghost btn-block"
            disabled={connecting}
            onClick={() => void openRoom('training')}
          >
            🤖 훈련장 (웨이브 · 봇이 반격합니다)
          </button>
        </section>
      </div>
    </div>
  );
}
