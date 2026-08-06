// 방 대기실: 코드 공유 / 참가자 목록 / 맵 선택(방장) / 게임 시작
import { useCallback, useEffect, useRef, useState } from 'react';
import MapPicker from '@/components/MapPicker';
import PlayerLeftNotice from '@/components/PlayerLeftNotice';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';

interface Props {
  onLeave: () => void;
}

export default function RoomScreen({ onLeave }: Props) {
  const room = useGameStore((s) => s.room);
  const playerId = useGameStore((s) => s.playerId);
  const error = useGameStore((s) => s.error);

  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    },
    [],
  );

  const copyCode = useCallback(async () => {
    if (!room) return;
    try {
      await navigator.clipboard.writeText(room.code);
    } catch {
      return; // 권한이 없으면 조용히 무시(코드는 화면에 보인다)
    }
    setCopied(true);
    if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
  }, [room]);

  const selectMap = useCallback((mapId: string) => {
    net.send({ type: 'set_map', map_id: mapId });
  }, []);

  if (!room) return null;

  const players = room.players;
  // 방장 = 가장 먼저 들어온 사람
  const isHost = players.length > 0 && players[0].id === playerId;
  const canStart = isHost && players.length >= 2;
  const emptySlots = Math.max(0, room.max_players - players.length);

  return (
    <div className="screen">
      <header className="brand">
        <h1>ROOM</h1>
      </header>

      {error ? (
        <div className="alert" role="alert">
          {error}
        </div>
      ) : null}

      <PlayerLeftNotice variant="room" />

      <div className="room-grid">
        <section className="panel">
          <div className="room-code">
            <strong aria-label={`Room code ${room.code.split('').join(' ')}`}>{room.code}</strong>
            <button type="button" className="btn" onClick={() => void copyCode()}>
              {copied ? 'COPIED!' : 'COPY CODE'}
            </button>
          </div>
          <p className="hint" style={{ textAlign: 'center' }}>
            Share this code with a friend. ({players.length} / {room.max_players})
          </p>

          <div className="divider" />

          <ul className="player-list">
            {players.map((p) => (
              <li key={p.id} className={`player-item${p.id === playerId ? ' is-me' : ''}`}>
                <span className="player-dot" style={{ background: p.customization.color }} />
                <span className="player-name">{p.nickname || 'Guest'}</span>
                <span className="player-tag">
                  {p.id === players[0]?.id ? 'HOST' : ''}
                  {p.id === playerId ? ' (YOU)' : ''}
                </span>
              </li>
            ))}
            {Array.from({ length: emptySlots }, (_, i) => (
              <li key={`slot-${i}`} className="player-item player-slot">
                Empty
              </li>
            ))}
          </ul>

          <div className="room-actions">
            <button type="button" className="btn btn-ghost" onClick={onLeave}>
              LEAVE
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canStart}
              onClick={() => net.send({ type: 'start_game' })}
            >
              START GAME
            </button>
          </div>

          {!isHost ? <p className="hint">Waiting for the host to start…</p> : null}
          {isHost && !canStart ? <p className="hint">You need at least 2 players to start.</p> : null}
        </section>

        <section className="panel">
          <MapPicker
            selected={room.map_id}
            active={room.map ?? null}
            canEdit={isHost}
            onSelect={selectMap}
          />
        </section>
      </div>
    </div>
  );
}
