// 대기실 맵 선택기. 방장만 고를 수 있고, 나머지는 방장의 선택을 그대로 본다.
// 카탈로그는 REST(GET /api/maps)로 한 번만 받아 온다 — 발판 좌표까지 들어 있어 미리보기를 그린다.
import { memo, useEffect, useState } from 'react';
import type { JSX, ReactNode } from 'react';
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
  /**
   * 제목 옆에 붙는 자리. 대기실이 여기에 대전 방식(일반전/경쟁전) 뱃지를 끼운다.
   * MapPicker 는 내용이 뭔지 모른다 — 맵 선택기가 경쟁전을 알 이유가 없다.
   */
  action?: ReactNode;
  /**
   * 맵을 못 고를 때 보여줄 문장. 기본값은 "방장만 바꿀 수 있어요" 인데, 경쟁전처럼
   * **방장도 못 고르는** 경우가 있어서 호출부가 갈아끼울 수 있어야 한다.
   */
  lockNote?: ReactNode;
}

function MapPickerInner({
  selected,
  active,
  canEdit,
  onSelect,
  action,
  lockNote,
}: Props): JSX.Element {
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
        <div className="map-picker-title">
          <h3 className="section-title">맵 선택</h3>
          {action}
        </div>
        <p className="map-picker-now">
          {isRandom ? (
            <>
              <strong>🎲 무작위</strong>
              <span className="hint"> — 라운드마다 맵이 바뀝니다</span>
            </>
          ) : current ? (
            <>
              <strong>
                {current.emoji} {current.name}
              </strong>
              <span className="hint"> — {current.desc}</span>
            </>
          ) : (
            <span className="hint">불러오는 중…</span>
          )}
        </p>
      </div>

      {failed ? (
        <p className="hint">맵 목록을 불러오지 못했습니다. 기본 맵으로 진행됩니다.</p>
      ) : (
        <div className="map-grid">
          {tile(RANDOM_MAP_ID, '무작위', '🎲', active, true)}
          {maps.map((m) => tile(m.id, m.name, m.emoji, m, false))}
        </div>
      )}

      {!canEdit ? <p className="hint">{lockNote ?? '맵은 방장만 바꿀 수 있어요.'}</p> : null}
    </div>
  );
}

export const MapPicker = memo(MapPickerInner);
export default MapPicker;
