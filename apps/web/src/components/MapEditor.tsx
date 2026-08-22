// 대기실 맵 에디터(방장 전용). 1280x720 월드 좌표를 그대로 쓰는 SVG 위에서
// 격자에 맞춰 블럭을 놓고 지우고, 저장하면 set_platforms 로 서버에 넘긴다.
//
// 맵 원본 지형도 그대로 불러와 편집 대상이 된다 — 지우개로 지울 수 있고, 고른 블럭은
// 크기·위치를 자유롭게 고칠 수 있다. 검증은 서버 game/blocks.py 가 다시 하므로
// 여기서는 편집 경험만 책임진다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { JSX, PointerEvent as ReactPointerEvent } from 'react';
import { BLOCK_INFO, BLOCK_TYPES, WORLD_HEIGHT, WORLD_WIDTH } from '@/types/game';
import type { BlockType, MapInfo, Platform } from '@/types/game';
import { deleteLayout, listLayouts, saveLayout } from '@/game/layoutStore';
import type { SavedLayout } from '@/game/layoutStore';

/** 서버 blocks.MAX_BLOCKS / MIN_SIZE 와 같은 값이어야 한다. */
const MAX_BLOCKS = 160;
const MIN_SIZE = 10;
/** 격자 칸 크기(월드 px). 클릭 한 번이면 이 크기의 블럭 하나가 놓인다. */
const GRID = 20;

/** 크기 조절 손잡이(하얀 네모)의 한 변. 블럭이 작으면 같이 작아진다 —
 *  고정 크기로 두면 최소 크기(10px) 블럭을 손잡이가 통째로 덮어 버려서 안 보인다. */
const HANDLE_MAX = 9;
const HANDLE_MIN = 4;
/** 보이는 크기와 별개로, 마우스로 집을 수 있는 범위. 작아져도 잡기 힘들면 안 된다. */
const HANDLE_GRAB = 15;
/** 변 가운데 손잡이를 보여 줄 최소 변 길이. 이보다 짧으면 모서리 손잡이와 겹친다. */
const MID_HANDLE_MIN_SIDE = 44;

/** 팔레트에서 고르는 도구 = 블럭 종류 + 지우개 */
type Tool = BlockType | 'eraser';
/** 선택한 블럭의 크기 조절 손잡이 */
type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

interface Drag {
  kind: 'draw' | 'move' | 'resize' | 'erase';
  /** 드래그를 시작한 월드 좌표(격자 스냅 전 원본) */
  fromX: number;
  fromY: number;
  index: number;
  handle: Handle | null;
  /** move/resize 를 시작한 순간의 사각형 */
  base: Platform | null;
}

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

/** 월드 밖으로 나가지 않고 최소 크기를 지키는 사각형으로 다듬는다. */
function fitToWorld(block: Platform): Platform {
  const width = clamp(block.width, MIN_SIZE, WORLD_WIDTH);
  const height = clamp(block.height, MIN_SIZE, WORLD_HEIGHT);
  return {
    ...block,
    width,
    height,
    x: clamp(block.x, 0, WORLD_WIDTH - width),
    y: clamp(block.y, 0, WORLD_HEIGHT - height),
  };
}

function hits(block: Platform, x: number, y: number): boolean {
  return (
    x >= block.x && x <= block.x + block.width && y >= block.y && y <= block.y + block.height
  );
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

/** 손잡이를 끈 만큼 사각형을 늘이거나 줄인다(뒤집히면 정규화). */
function resized(base: Platform, handle: Handle, dx: number, dy: number): Platform {
  let { x, y, width, height } = base;
  if (handle.includes('w')) {
    x = base.x + dx;
    width = base.width - dx;
  }
  if (handle.includes('e')) width = base.width + dx;
  if (handle.includes('n')) {
    y = base.y + dy;
    height = base.height - dy;
  }
  if (handle.includes('s')) height = base.height + dy;
  if (width < 0) {
    x += width;
    width = -width;
  }
  if (height < 0) {
    y += height;
    height = -height;
  }
  return fitToWorld({ ...base, x, y, width, height });
}

/** 이동발판은 저마다 움직임이 달라 합치면 안 된다. 나머지는 붙어 있으면 하나로. */
function sameKind(a: Platform, b: Platform): boolean {
  const ka = a.type ?? 'solid';
  if (ka === 'mover' || ka !== (b.type ?? 'solid')) return false;
  return (a.power ?? 0) === (b.power ?? 0);
}

/**
 * 맞닿은 같은 종류의 블럭을 한 덩어리로 합친다(가로 → 세로).
 * 격자로 칠하면 칸이 금방 수백 개가 되므로, 서버로 보내기 전에 여기서 줄인다.
 */
function mergeBlocks(list: Platform[]): Platform[] {
  const merge = (input: Platform[], vertical: boolean): Platform[] => {
    const out: Platform[] = [];
    const rest = [...input].sort((a, b) =>
      vertical ? a.x - b.x || a.y - b.y : a.y - b.y || a.x - b.x,
    );
    for (const block of rest) {
      const prev = out[out.length - 1];
      const joins = vertical
        ? prev && prev.x === block.x && prev.width === block.width && prev.y + prev.height === block.y
        : prev && prev.y === block.y && prev.height === block.height && prev.x + prev.width === block.x;
      if (prev && joins && sameKind(prev, block)) {
        if (vertical) prev.height += block.height;
        else prev.width += block.width;
        continue;
      }
      out.push({ ...block });
    }
    return out;
  };
  return merge(merge(list, false), true);
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
  const [tool, setTool] = useState<Tool>('solid');
  const [selected, setSelected] = useState<number | null>(null);
  // 드래그로 그리는 중인 사각형(월드 좌표). null 이면 그리는 중이 아니다.
  const [draft, setDraft] = useState<Platform | null>(null);
  const drag = useRef<Drag | null>(null);

  const [saved, setSaved] = useState<SavedLayout[]>(() => listLayouts());
  const [slotName, setSlotName] = useState('');

  const brush: BlockType = tool === 'eraser' ? 'solid' : tool;
  const full = blocks.length >= MAX_BLOCKS;
  const current = selected !== null ? (blocks[selected] ?? null) : null;

  /** 겹쳐 있으면 나중에 놓은(위에 그려진) 블럭을 먼저 집는다. */
  const blockAt = useCallback(
    (x: number, y: number): number => {
      for (let i = blocks.length - 1; i >= 0; i -= 1) {
        if (hits(blocks[i], x, y)) return i;
      }
      return -1;
    },
    [blocks],
  );

  const removeAt = useCallback((index: number) => {
    setBlocks((list) => list.filter((_, i) => i !== index));
    setSelected((sel) => (sel === null || sel === index ? null : sel > index ? sel - 1 : sel));
  }, []);

  const patch = useCallback((index: number, changes: Partial<Platform>) => {
    setBlocks((list) => list.map((b, i) => (i === index ? fitToWorld({ ...b, ...changes }) : b)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (selected === null) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        removeAt(selected);
        return;
      }
      // 화살표로 미세 조정: 그냥 누르면 한 칸 이동, Shift 를 누르면 크기 조절.
      const dx = (e.key === 'ArrowRight' ? GRID : 0) - (e.key === 'ArrowLeft' ? GRID : 0);
      const dy = (e.key === 'ArrowDown' ? GRID : 0) - (e.key === 'ArrowUp' ? GRID : 0);
      if (dx === 0 && dy === 0) return;
      e.preventDefault();
      setBlocks((list) =>
        list.map((b, i) => {
          if (i !== selected) return b;
          return e.shiftKey
            ? fitToWorld({ ...b, width: b.width + dx, height: b.height + dy })
            : fitToWorld({ ...b, x: b.x + dx, y: b.y + dy });
        }),
      );
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, removeAt, selected]);

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
      const at = toWorld(e);
      if (!at) return;
      e.currentTarget.setPointerCapture(e.pointerId);

      // 우클릭은 도구와 상관없이 언제나 지우개다(원본 지형도 여기서 지운다).
      const erasing = e.button === 2 || tool === 'eraser';
      if (erasing) {
        drag.current = { kind: 'erase', fromX: at.x, fromY: at.y, index: -1, handle: null, base: null };
        const index = blockAt(at.x, at.y);
        if (index >= 0) removeAt(index);
        return;
      }

      const index = blockAt(at.x, at.y);
      if (index >= 0) {
        // 기존 블럭 위에서는 새로 그리지 않고 집어서 옮긴다.
        setSelected(index);
        setTool(blocks[index].type ?? 'solid');
        drag.current = {
          kind: 'move',
          fromX: at.x,
          fromY: at.y,
          index,
          handle: null,
          base: { ...blocks[index] },
        };
        return;
      }

      if (full) return;
      setSelected(null);
      drag.current = { kind: 'draw', fromX: at.x, fromY: at.y, index: -1, handle: null, base: null };
    },
    [blockAt, blocks, full, removeAt, tool, toWorld],
  );

  const startResize = useCallback(
    (e: ReactPointerEvent, handle: Handle) => {
      if (selected === null) return;
      const at = toWorld(e);
      if (!at) return;
      e.stopPropagation();
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
      drag.current = {
        kind: 'resize',
        fromX: at.x,
        fromY: at.y,
        index: selected,
        handle,
        base: { ...blocks[selected] },
      };
    },
    [blocks, selected, toWorld],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<SVGSVGElement>) => {
      const state = drag.current;
      if (!state) return;
      const at = toWorld(e);
      if (!at) return;

      if (state.kind === 'erase') {
        const index = blockAt(at.x, at.y);
        if (index >= 0) removeAt(index);
        return;
      }

      const dx = snapTo(at.x - state.fromX);
      const dy = snapTo(at.y - state.fromY);

      if (state.kind === 'move' && state.base) {
        patch(state.index, { x: state.base.x + dx, y: state.base.y + dy });
        return;
      }
      if (state.kind === 'resize' && state.base && state.handle) {
        setBlocks((list) =>
          list.map((b, i) => (i === state.index ? resized(state.base!, state.handle!, dx, dy) : b)),
        );
        return;
      }

      const x1 = clamp(snapTo(state.fromX), 0, WORLD_WIDTH);
      const y1 = clamp(snapTo(state.fromY), 0, WORLD_HEIGHT);
      const x2 = clamp(snapTo(at.x), 0, WORLD_WIDTH);
      const y2 = clamp(snapTo(at.y), 0, WORLD_HEIGHT);
      setDraft(
        withDefaults(
          {
            x: Math.min(x1, x2),
            y: Math.min(y1, y2),
            width: Math.abs(x2 - x1),
            height: Math.abs(y2 - y1),
          },
          brush,
        ),
      );
    },
    [blockAt, brush, patch, removeAt, toWorld],
  );

  const onPointerUp = useCallback(() => {
    const state = drag.current;
    drag.current = null;
    setDraft(null);
    if (!state || state.kind !== 'draw') return;

    // 드래그 없이 톡 눌렀으면 격자 한 칸을 놓는다(그림판처럼 콕콕 찍어 칠할 수 있게).
    const cell = draft && draft.width >= MIN_SIZE && draft.height >= MIN_SIZE
      ? draft
      : withDefaults(
          {
            x: clamp(Math.floor(state.fromX / GRID) * GRID, 0, WORLD_WIDTH - GRID),
            y: clamp(Math.floor(state.fromY / GRID) * GRID, 0, WORLD_HEIGHT - GRID),
            width: GRID,
            height: GRID,
          },
          brush,
        );

    if (blocks.length >= MAX_BLOCKS) return;
    setBlocks((list) => (list.length >= MAX_BLOCKS ? list : [...list, fitToWorld(cell)]));
    setSelected(blocks.length);
  }, [blocks.length, brush, draft]);

  const pickTool = useCallback(
    (next: Tool) => {
      setTool(next);
      if (next === 'eraser') {
        setSelected(null);
        return;
      }
      // 블럭을 고른 채로 종류를 바꾸면 그 블럭의 종류가 바뀐다.
      if (selected !== null) {
        setBlocks((list) => list.map((b, i) => (i === selected ? withDefaults(b, next) : b)));
      }
    },
    [selected],
  );

  const gridLines = useMemo(() => {
    const lines: JSX.Element[] = [];
    for (let x = GRID; x < WORLD_WIDTH; x += GRID) {
      lines.push(<line key={`v${x}`} x1={x} y1={0} x2={x} y2={WORLD_HEIGHT} />);
    }
    for (let y = GRID; y < WORLD_HEIGHT; y += GRID) {
      lines.push(<line key={`h${y}`} x1={0} y1={y} x2={WORLD_WIDTH} y2={y} />);
    }
    return lines;
  }, []);

  const handles: Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
  const handleAt = (block: Platform, handle: Handle): { x: number; y: number } => ({
    x: block.x + (handle.includes('w') ? 0 : handle.includes('e') ? block.width : block.width / 2),
    y: block.y + (handle.includes('n') ? 0 : handle.includes('s') ? block.height : block.height / 2),
  });
  /** 손잡이 한 변. 작은 블럭에서는 블럭이 보이도록 같이 줄어든다. */
  const handleSize = (block: Platform): number =>
    clamp(Math.min(block.width, block.height) * 0.45, HANDLE_MIN, HANDLE_MAX);
  /** 변 가운데 손잡이(n/s/e/w)는 그만한 여유가 있을 때만 그린다. */
  const visibleHandles = (block: Platform): Handle[] =>
    handles.filter((h) => {
      if (h === 'n' || h === 's') return block.width >= MID_HANDLE_MIN_SIDE;
      if (h === 'e' || h === 'w') return block.height >= MID_HANDLE_MIN_SIDE;
      return true;
    });

  const store = useCallback(() => {
    const name = slotName.trim() || `${map.name} 배치`;
    setSaved(saveLayout(name, map.id, mergeBlocks(blocks)));
    setSlotName('');
  }, [blocks, map.id, map.name, slotName]);

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
                  className={`editor-brush${tool === t ? ' selected' : ''}`}
                  aria-pressed={tool === t}
                  title={BLOCK_INFO[t].desc}
                  onClick={() => pickTool(t)}
                >
                  <span className="editor-swatch" style={{ background: BLOCK_INFO[t].color }} aria-hidden />
                  {BLOCK_INFO[t].name}
                </button>
              ))}
              <button
                type="button"
                className={`editor-brush${tool === 'eraser' ? ' selected' : ''}`}
                aria-pressed={tool === 'eraser'}
                title="맵 원본 지형까지 지울 수 있습니다. 우클릭도 같은 기능이에요."
                onClick={() => pickTool('eraser')}
              >
                <span className="editor-swatch editor-swatch-eraser" aria-hidden />
                지우개
              </button>
            </div>
            <p className="hint">
              {tool === 'eraser'
                ? '지울 블럭을 누르거나 훑으세요. 맵 원본 지형도 지워집니다.'
                : BLOCK_INFO[brush].desc}
            </p>

            <div className="divider" />

            {current ? (
              <>
                <h3 className="label">선택한 블럭</h3>
                <div className="editor-nums">
                  {(
                    [
                      ['x', 'X', 0, WORLD_WIDTH],
                      ['y', 'Y', 0, WORLD_HEIGHT],
                      ['width', '너비', MIN_SIZE, WORLD_WIDTH],
                      ['height', '높이', MIN_SIZE, WORLD_HEIGHT],
                    ] as const
                  ).map(([key, label, lo, hi]) => (
                    <label key={key} className="editor-num">
                      {label}
                      <input
                        className="input"
                        type="number"
                        min={lo}
                        max={hi}
                        step={1}
                        value={Math.round(current[key])}
                        onChange={(e) => patch(selected!, { [key]: Number(e.target.value) })}
                      />
                    </label>
                  ))}
                </div>
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
                  onClick={() => removeAt(selected!)}
                >
                  🗑 이 블럭 지우기 (Del)
                </button>
              </>
            ) : (
              <p className="hint">
                빈 칸을 누르면 한 칸, 드래그하면 그만큼 놓입니다. 블럭을 집으면 끌어 옮기고
                모서리로 크기를 바꿀 수 있어요(화살표 키로 한 칸씩, Shift+화살표로 크기 조절).
              </p>
            )}

            <div className="divider" />

            <h3 className="label">저장된 배치</h3>
            <div className="editor-save">
              <input
                className="input"
                type="text"
                value={slotName}
                maxLength={24}
                placeholder="이름 (예: 내 협곡)"
                onChange={(e) => setSlotName(e.target.value)}
              />
              <button type="button" className="btn" onClick={store} disabled={blocks.length === 0}>
                저장
              </button>
            </div>
            <ul className="editor-slots">
              {saved.map((slot) => (
                <li key={slot.name}>
                  <button
                    type="button"
                    className="editor-slot"
                    title={`${slot.blocks.length}개 블럭 · ${slot.map}`}
                    onClick={() => {
                      setBlocks(slot.blocks.map((b) => withDefaults(b, b.type ?? 'solid')));
                      setSelected(null);
                    }}
                  >
                    {slot.name} <span className="hint">({slot.blocks.length})</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost editor-slot-x"
                    aria-label={`${slot.name} 삭제`}
                    onClick={() => setSaved(deleteLayout(slot.name))}
                  >
                    ✕
                  </button>
                </li>
              ))}
              {saved.length === 0 ? <li className="hint">아직 저장한 배치가 없어요.</li> : null}
            </ul>
          </div>

          <div className="editor-stage">
            <svg
              ref={svgRef}
              className={`editor-canvas${tool === 'eraser' ? ' is-erasing' : ''}`}
              viewBox={`0 0 ${WORLD_WIDTH} ${WORLD_HEIGHT}`}
              preserveAspectRatio="xMidYMid meet"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              onContextMenu={(e) => e.preventDefault()}
            >
              <rect x={0} y={0} width={WORLD_WIDTH} height={WORLD_HEIGHT} fill={map.theme.bg} />
              <g className="editor-grid" stroke={map.theme.edge} strokeOpacity={0.18} strokeWidth={1}>
                {gridLines}
              </g>
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
                  pointerEvents="none"
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
                    strokeWidth={i === selected ? 4 : 1.5}
                    pointerEvents="none"
                  />
                );
              })}
              {current ? (
                <g>
                  {visibleHandles(current).map((h) => {
                    const at = handleAt(current, h);
                    const s = handleSize(current);
                    return (
                      <g
                        key={h}
                        style={{ cursor: `${h}-resize` }}
                        onPointerDown={(e) => startResize(e, h)}
                      >
                        {/* 보이는 네모는 작게 — 크면 최소 크기 블럭을 통째로 가린다 */}
                        <rect
                          x={at.x - s / 2}
                          y={at.y - s / 2}
                          width={s}
                          height={s}
                          fill="#ffffff"
                          stroke="#0b0d17"
                          strokeWidth={1.5}
                          pointerEvents="none"
                        />
                        {/* 집는 범위는 보이는 크기와 따로 넓게 둔다 */}
                        <rect
                          x={at.x - HANDLE_GRAB / 2}
                          y={at.y - HANDLE_GRAB / 2}
                          width={HANDLE_GRAB}
                          height={HANDLE_GRAB}
                          fill="transparent"
                        />
                      </g>
                    );
                  })}
                </g>
              ) : null}
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
                  pointerEvents="none"
                />
              ) : null}
            </svg>
            <p className="hint editor-count">
              좌클릭: 배치 · 우클릭/지우개: 삭제 · 드래그: 연속 · 블럭 {blocks.length} / {MAX_BLOCKS}
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
            <button type="button" className="btn btn-ghost" onClick={() => setBlocks([])}>
              전부 지우기
            </button>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              취소
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={blocks.length === 0}
              onClick={() => {
                onSave(mergeBlocks(blocks));
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
