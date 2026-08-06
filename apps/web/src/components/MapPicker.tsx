// 대기실 맵 선택기. 방장만 고를 수 있고, 나머지는 방장의 선택을 그대로 본다.
// 카탈로그는 REST(GET /api/maps)로 한 번만 받아 온다 — 발판 좌표까지 들어 있어 미리보기를 그린다.
import { memo, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { api } from '@/api/client';
import MapPreview from '@/components/MapPreview';
import { RANDOM_MAP_ID } from '@/types/game';
import type { MapInfo } from '@/types/game';

interface Props {
  /** 방장이 고른 값(RoomState.map_id). 'random' 일 수 있다. */
  selected: string;
  /** 지금 실제로 깔려 있는 맵(RoomState.map) — '무작위' 타일의 미리보기로 쓴다. */
  active: MapInfo | null;
  canEdit: boolean;
  onSelect(mapId: string): void;
}

function MapPickerInner({ selected, active, canEdit, onSelect }: Props): JSX.Element {
  const [maps, setMaps] = useState<MapInfo[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getMaps()
      .then((list) => {
        if (alive) setMaps(list);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const isRandom = selected === RANDOM_MAP_ID;
  const current = maps.find((m) => m.id === selected) ?? null;

  const tile = (
    id: string,
    name: string,
    emoji: string,
    preview: MapInfo | null,
    dice: boolean,
  ): JSX.Element => {
    const chosen = selected === id;
    return (
      <button
        type="button"
        key={id}
        className={`map-tile${chosen ? ' selected' : ''}${dice ? ' dice' : ''}`}
        disabled={!canEdit}
        aria-pressed={chosen}
        onClick={() => onSelect(id)}
      >
        <span className="map-tile-art">
          {preview ? <MapPreview map={preview} showSpawns={false} /> : null}
          {dice ? <span className="map-tile-dice">🎲</span> : null}
        </span>
        <span className="map-tile-name">
          <span aria-hidden>{emoji}</span> {name}
        </span>
      </button>
    );
  };

  return (
    <div className="map-picker">
      <div className="map-picker-head">
        <h3 className="section-title">MAP</h3>
        <p className="map-picker-now">
          {isRandom ? (
            <>
              <strong>🎲 Random</strong>
              <span className="hint"> — the map changes every round</span>
            </>
          ) : current ? (
            <>
              <strong>
                {current.emoji} {current.name}
              </strong>
              <span className="hint"> — {current.desc}</span>
            </>
          ) : (
            <span className="hint">Loading…</span>
          )}
        </p>
      </div>

      {failed ? (
        <p className="hint">Could not load the map list. The default map will be used.</p>
      ) : (
        <div className="map-grid">
          {tile(RANDOM_MAP_ID, 'Random', '🎲', active, true)}
          {maps.map((m) => tile(m.id, m.name, m.emoji, m, false))}
        </div>
      )}

      {!canEdit ? <p className="hint">Only the host can change the map.</p> : null}
    </div>
  );
}

export const MapPicker = memo(MapPickerInner);
export default MapPicker;
