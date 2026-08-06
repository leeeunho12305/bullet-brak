// 로비: 닉네임 / 외형 / 코인 + 방 만들기 · 코드로 참가 · 훈련 모드
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import AvatarEditor from '@/components/AvatarEditor';
import { ApiError, api } from '@/api/client';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import { useLocalProfile } from '@/hooks/useLocalProfile';
import { RANDOM_MAP_ID } from '@/types/game';
import type { MapInfo } from '@/types/game';

const NICKNAME_MAX = 12;
const CODE_LENGTH = 6;

function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return 'Something went wrong.';
}

export default function LobbyScreen() {
  const { nickname, customization, coins, setNickname } = useLocalProfile();
  const status = useGameStore((s) => s.status);
  const storeError = useGameStore((s) => s.error);

  const [code, setCode] = useState('');
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [mapId, setMapId] = useState<string>(RANDOM_MAP_ID);
  const [maps, setMaps] = useState<MapInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // 시작 맵. 방을 만든 뒤 대기실에서 방장이 언제든 바꿀 수 있다.
  useEffect(() => {
    let alive = true;
    api
      .getMaps()
      .then((list) => {
        if (alive) setMaps(list);
      })
      .catch(() => {
        /* 목록을 못 받으면 select 가 '무작위' 하나만 남는다 — 서버가 알아서 고른다 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const connecting = status === 'connecting' || busy;
  const message = localError ?? storeError;

  const profile = useCallback(
    () => ({
      nickname: nickname.trim() || 'Guest',
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
          map_id: mapId,
        });
        net.connect(room.code, profile());
      } catch (e) {
        setLocalError(errorText(e));
      } finally {
        setBusy(false);
      }
    },
    [mapId, maxPlayers, profile],
  );

  const joinRoom = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      if (code.length !== CODE_LENGTH) {
        setLocalError(`Enter the ${CODE_LENGTH}-digit room code.`);
        return;
      }
      setLocalError(null);
      setBusy(true);
      try {
        // 먼저 방 존재를 확인해 두면 실패 메시지를 바로 보여줄 수 있다.
        await api.getRoom(code);
        net.connect(code, profile());
      } catch (e) {
        setLocalError(e instanceof ApiError && e.status === 404 ? 'Room not found.' : errorText(e));
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
          <h2 className="section-title">PLAYER</h2>

          <div className="field">
            <label className="label" htmlFor="nickname">
              Nickname
            </label>
            <input
              id="nickname"
              className="input"
              value={nickname}
              maxLength={NICKNAME_MAX}
              placeholder="Guest"
              autoComplete="off"
              onChange={(e) => setNickname(e.target.value.slice(0, NICKNAME_MAX))}
            />
          </div>

          {/* 외형 편집기(동료 컴포넌트) — store 의 customization 을 직접 갱신한다 */}
          <AvatarEditor />
        </section>

        <section className="panel">
          <h2 className="section-title">PLAY</h2>

          <div className="field">
            <label className="label" htmlFor="maxPlayers">
              Room size
            </label>
            <select
              id="maxPlayers"
              className="input"
              value={maxPlayers}
              onChange={(e) => setMaxPlayers(Number(e.target.value))}
            >
              <option value={2}>2 players</option>
              <option value={3}>3 players</option>
              <option value={4}>4 players</option>
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="mapId">
              Map
            </label>
            <select
              id="mapId"
              className="input"
              value={mapId}
              onChange={(e) => setMapId(e.target.value)}
            >
              <option value={RANDOM_MAP_ID}>🎲 Random (new map each round)</option>
              {maps.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.emoji} {m.name}
                </option>
              ))}
            </select>
            <p className="hint">The host can change this in the room.</p>
          </div>

          <button
            type="button"
            className="btn btn-primary btn-block"
            disabled={connecting}
            onClick={() => void openRoom('pvp')}
          >
            {connecting ? <span className="spinner" aria-hidden /> : null}
            CREATE ROOM
          </button>

          <div className="divider" />

          <form onSubmit={(e) => void joinRoom(e)}>
            <label className="label" htmlFor="roomCode">
              Join with code
            </label>
            <div className="row">
              <input
                id="roomCode"
                className="input code-input"
                value={code}
                inputMode="numeric"
                autoComplete="off"
                placeholder="000000"
                aria-label="Room code, 6 digits"
                onChange={(e) =>
                  setCode(e.target.value.toUpperCase().replace(/[^0-9]/g, '').slice(0, CODE_LENGTH))
                }
              />
              <button
                type="submit"
                className="btn"
                disabled={connecting || code.length !== CODE_LENGTH}
              >
                JOIN
              </button>
            </div>
            <p className="hint">Press Enter to join right away.</p>
          </form>

          <div className="divider" />

          <button
            type="button"
            className="btn btn-ghost btn-block"
            disabled={connecting}
            onClick={() => void openRoom('training')}
          >
            🤖 TRAINING (waves · bots shoot back)
          </button>
        </section>
      </div>
    </div>
  );
}
