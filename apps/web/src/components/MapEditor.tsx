// 대기실 맵 에디터(방장 전용). 800x600 월드 좌표를 그대로 쓰는 SVG 위에서
// 블럭을 끌어 그리고, 저장하면 set_platforms 로 서버에 넘긴다.
//
// 검증은 서버 game/blocks.py 가 다시 하므로 여기서는 편집 경험만 책임진다.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX, PointerEvent as ReactPointerEvent } from 'react';
import { BLOCK_INFO, BLOCK_TYPES, WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { BlockType, MapInfo, Platform } from '@/types/game';

/** 서버 blocks.MAX_BLOCKS / MIN_SIZE 와 같은 값이어야 한다. */
const MAX_BLOCKS = 40;
const MIN_SIZE = 10;
/** 격자 스냅 간격(월드 px) */
const GRID = 10;

interface Props {
  map: MapInfo;
  /** 지금 방에 깔린 발판(= RoomState.map.platforms) */
  platforms: Platform[];
  /** 맵 원본이 아니라 편집된 배치인가 */
  edited: boolean;
  onSave(platforms: Platform[]): void;
  onReset(): void;
  onClose(): void;
}

function snapTo(v: number): number {
  return Math.round(v / GRID) * GRID;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * 종류를 바꿀 때 그 종류에 필요한 필드만 남긴다(크기는 유지).
 * 이미 갖고 있던 값은 살린다 — 이동발판을 다시 열었을 때 왕복 폭이 초기화되면 안 된다.
 */
function withDefaults(block: Platform, kind: BlockType): Platform {
  const next: Platform = { ...block, type: kind };
  delete next.power;
  delete next.axis;
  delete next.span;
  delete next.speed;
  if (kind === 'jump') next.power = block.power ?? 21;
  if (kind === 'mover') {
    next.axis = block.axis ?? 'x';
    next.span = block.span ?? 120;
    next.speed = block.speed ?? 0.9;
  }
  return next;
}

export default function MapEditor({
  map,
  platforms,
  edited,
  onSave,
  onReset,
  onClose,
}: Props): JSX.Element {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [blocks, setBlocks] = useState<Platform[]>(() =>
    platforms.map((p) => withDefaults(p, p.type ?? 'solid')),
  );
  const [brush, setBrush] = useState<BlockType>('solid');
  const [selected, setSelected] = useState<number | null>(null);
  // 드래그로 그리는 중인 사각형(월드 좌표). null 이면 그리는 중이 아니다.
  const [draft, setDraft] = useState<Platform | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);

  const full = blocks.length >= MAX_BLOCKS;

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected !== null) {
        setBlocks((list) => list.filter((_, i) => i !== selected));
        setSelected(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, selected]);

  /** 화면 좌표 → 월드 좌표 (SVG 가 어떤 크기로 늘어나 있든 맞춘다) */
  const toWorld = useCallback((e: ReactPointerEvent): { x: number; y: number } | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const box = svg.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return null;
    return {
      x: ((e.clientX - box.left) / box.width) * WORLD_WIDTH,
      y: ((e.clientY - box.top) / box.height) * WORLD_HEIGHT,
    };
  }, []);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<SVGSVGElement>) => {
      if (full) return;
      const at = toWorld(e);
      if (!at) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      dragStart.current = { x: snapTo(at.x), y: snapTo(at.y) };
      setSelected(null);
    },
    [full, toWorld],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<SVGSVGElement>) => {
      const start = dragStart.current;
      if (!start) return;
      const at = toWorld(e);
      if (!at) return;
      const x2 = clamp(snapTo(at.x), 0, WORLD_WIDTH);
      const y2 = clamp(snapTo(at.y), 0, WORLD_HEIGHT);
      setDraft(
        withDefaults(
          {
            x: Math.min(start.x, x2),
            y: Math.min(start.y, y2),
            width: Math.abs(x2 - start.x),
            height: Math.abs(y2 - start.y),
          },
          brush,
        ),
      );
    },
    [brush, toWorld],
  );

  const onPointerUp = useCallback(() => {
    dragStart.current = null;
    setDraft(null);
    if (!draft) return;
    // 너무 작게 그린 것은 실수로 본다(클릭만 하고 만 경우).
    if (draft.width < MIN_SIZE || draft.height < MIN_SIZE) return;
    setBlocks((list) => (list.length >= MAX_BLOCKS ? list : [...list, draft]));
    setSelected(blocks.length);
  }, [blocks.length, draft]);

  const patch = useCallback((index: number, changes: Partial<Platform>) => {
    setBlocks((list) => list.map((b, i) => (i === index ? { ...b, ...changes } : b)));
  }, []);

  const current = selected !== null ? blocks[selected] : null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="맵 에디터">
      <div className="modal editor">
        <header className="modal-head">
          <h2>
            <span aria-hidden>🧱</span> 맵 에디터
            <span className="hint editor-sub">
              {map.emoji} {map.name}
              {edited ? ' · 편집됨' : ''}
            </span>
          </h2>
          <button type="button" className="btn btn-ghost modal-x" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </header>

        <div className="editor-body">
          <div className="editor-side">
            <h3 className="label">블럭</h3>
            <div className="editor-palette">
              {BLOCK_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`editor-brush${brush === t ? ' selected' : ''}`}
                  aria-pressed={brush === t}
                  title={BLOCK_INFO[t].desc}
                  onClick={() => {
                    setBrush(t);
                    if (selected !== null) {
                      setBlocks((list) =>
                        list.map((b, i) => (i === selected ? withDefaults(b, t) : b)),
                      );
                    }
                  }}
                >
                  <span className="editor-swatch" style={{ background: BLOCK_INFO[t].color }} aria-hidden />
                  {BLOCK_INFO[t].name}
                </button>
              ))}
            </div>
            <p className="hint">{BLOCK_INFO[brush].desc}</p>

            <div className="divider" />

            {current ? (
              <>
                <h3 className="label">선택한 블럭</h3>
                {current.type === 'jump' ? (
                  <label className="editor-field">
                    위력 <b>{Math.round(current.power ?? 21)}</b>
                    <input
                      type="range"
                      min={10}
                      max={34}
                      step={1}
                      value={current.power ?? 21}
                      onChange={(e) => patch(selected!, { power: Number(e.target.value) })}
                    />
                  </label>
                ) : null}
                {current.type === 'mover' ? (
                  <>
                    <label className="editor-field">
                      방향
                      <select
                        className="input"
                        value={current.axis ?? 'x'}
                        onChange={(e) => patch(selected!, { axis: e.target.value as 'x' | 'y' })}
                      >
                        <option value="x">↔ 좌우</option>
                        <option value="y">↕ 위아래</option>
                      </select>
                    </label>
                    <label className="editor-field">
                      왕복 폭 <b>{Math.round(current.span ?? 120)}px</b>
                      <input
                        type="range"
                        min={20}
                        max={400}
                        step={10}
                        value={current.span ?? 120}
                        onChange={(e) => patch(selected!, { span: Number(e.target.value) })}
                      />
                    </label>
                    <label className="editor-field">
                      속도 <b>{(current.speed ?? 0.9).toFixed(1)}</b>
                      <input
                        type="range"
                        min={0.1}
                        max={3}
                        step={0.1}
                        value={current.speed ?? 0.9}
                        onChange={(e) => patch(selected!, { speed: Number(e.target.value) })}
                      />
                    </label>
                  </>
                ) : null}
                <button
                  type="button"
                  className="btn btn-ghost btn-block"
                  onClick={() => {
                    setBlocks((list) => list.filter((_, i) => i !== selected));
                    setSelected(null);
                  }}
                >
                  🗑 이 블럭 지우기 (Del)
                </button>
              </>
            ) : (
              <p className="hint">
                빈 곳을 드래그하면 블럭이 생기고, 블럭을 클릭하면 설정을 바꿀 수 있어요.
              </p>
            )}
          </div>

          <div className="editor-stage">
            <svg
              ref={svgRef}
              className="editor-canvas"
              viewBox={`0 0 ${WORLD_WIDTH} ${WORLD_HEIGHT}`}
              preserveAspectRatio="xMidYMid meet"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <rect x={0} y={0} width={WORLD_WIDTH} height={WORLD_HEIGHT} fill={map.theme.bg} />
              {/* 스폰 지점은 못 옮기지만, 여기에 블럭을 겹치면 안 되므로 보여준다. */}
              {map.spawns.map((s, i) => (
                <circle
                  key={`sp${i}`}
                  cx={s.x + 15}
                  cy={s.y + 15}
                  r={15}
                  fill="none"
                  stroke={map.theme.edge}
                  strokeDasharray="6 5"
                  strokeWidth={3}
                />
              ))}
              {blocks.map((b, i) => {
                const kind = b.type ?? 'solid';
                return (
                  <rect
                    key={`b${i}`}
                    x={b.x}
                    y={b.y}
                    width={b.width}
                    height={b.height}
                    fill={BLOCK_INFO[kind].color}
                    fillOpacity={kind === 'solid' ? 0.55 : 0.75}
                    stroke={i === selected ? '#ffffff' : BLOCK_INFO[kind].color}
                    strokeWidth={i === selected ? 5 : 2}
                    style={{ cursor: 'pointer' }}
                    onPointerDown={(e) => {
                      // 기존 블럭 위에서는 새로 그리지 않고 선택만 한다.
                      e.stopPropagation();
                      setSelected(i);
                      setBrush(kind);
                    }}
                  />
                );
              })}
              {draft && draft.width >= MIN_SIZE && draft.height >= MIN_SIZE ? (
                <rect
                  x={draft.x}
                  y={draft.y}
                  width={draft.width}
                  height={draft.height}
                  fill={BLOCK_INFO[brush].color}
                  fillOpacity={0.35}
                  stroke="#fff"
                  strokeDasharray="8 6"
                  strokeWidth={3}
                />
              ) : null}
            </svg>
            <p className="hint editor-count">
              블럭 {blocks.length} / {MAX_BLOCKS}
              {full ? ' — 가득 찼습니다. 지워야 더 놓을 수 있어요.' : ''}
            </p>
          </div>
        </div>

        <footer className="modal-foot">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              onReset();
              onClose();
            }}
          >
            원래 지형으로
          </button>
          <div className="row">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              취소
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={blocks.length === 0}
              onClick={() => {
                onSave(blocks);
                onClose();
              }}
            >
              저장하고 적용
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
