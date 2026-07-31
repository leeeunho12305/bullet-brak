// 로비에서 쓰는 아바타 편집기. props 시그니처는 LobbyScreen 과의 계약이므로 바꾸지 않는다.
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useGameStore } from '@/store/gameStore';
import { COLORS, PART_TABLE, drawAvatar, drawPartThumbnail } from '@/game/avatars';
import type { PartCategory } from '@/game/avatars';
import type { PartOption } from '@/game/avatarParts';
import type { Customization } from '@/types/game';
import '@/styles/game.css';

const THUMB = 44;
const PREVIEW = 150;

const TABS: { key: PartCategory | 'color'; label: string }[] = [
  { key: 'eye', label: '눈' },
  { key: 'mouth', label: '입' },
  { key: 'detail', label: '디테일' },
  { key: 'color', label: '색상' },
];

interface StoreSlice {
  customization: Customization;
  setCustomization: (c: Customization) => void;
}

export interface AvatarEditorProps {
  /** 생략하면 store 의 customization 을 사용한다. */
  value?: Customization;
  /** 생략하면 store 의 setCustomization 을 호출한다. */
  onChange?: (c: Customization) => void;
}

interface ThumbProps {
  part: PartOption;
  color: string;
  selected: boolean;
  onSelect: () => void;
}

function PartThumb({ part, color, selected, onSelect }: ThumbProps): JSX.Element {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    drawPartThumbnail(ctx, part, THUMB, color);
  }, [part, color]);

  return (
    <button
      type="button"
      className={`ae-item${selected ? ' selected' : ''}`}
      onClick={onSelect}
      title={part.label}
    >
      <canvas ref={ref} width={THUMB * 2} height={THUMB * 2} style={{ width: THUMB, height: THUMB }} />
      <span className="ae-item-label">{part.label}</span>
    </button>
  );
}

const Thumb = memo(PartThumb);

function AvatarEditorInner(props: AvatarEditorProps): JSX.Element {
  const storeValue = useGameStore((s: StoreSlice) => s.customization);
  const storeSet = useGameStore((s: StoreSlice) => s.setCustomization);
  const value = props.value ?? storeValue;
  const onChange = props.onChange ?? storeSet;
  const [tab, setTab] = useState<PartCategory | 'color'>('eye');
  const previewRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = previewRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(2, 0, 0, 2, 0, 0);
    ctx.clearRect(0, 0, PREVIEW, PREVIEW);
    drawAvatar(ctx, value, 15, 15, PREVIEW - 30, PREVIEW - 30, { shadow: false });
  }, [value]);

  const setPart = useCallback(
    (category: PartCategory, index: number) => {
      const next: Customization = { ...value };
      if (category === 'eye') next.eye = index;
      else if (category === 'mouth') next.mouth = index;
      else next.detail = index;
      onChange(next);
    },
    [onChange, value],
  );

  const setColor = useCallback(
    (color: string) => {
      onChange({ ...value, color });
    },
    [onChange, value],
  );

  const parts = tab === 'color' ? null : PART_TABLE[tab];

  return (
    <div className="avatar-editor panel">
      <div className="ae-preview">
        <canvas
          ref={previewRef}
          width={PREVIEW * 2}
          height={PREVIEW * 2}
          style={{ width: PREVIEW, height: PREVIEW }}
          aria-label="캐릭터 미리보기"
        />
      </div>

      <div className="ae-side">
        <div className="ae-tabs">
          {TABS.map((t) => (
            <button
              type="button"
              key={t.key}
              className={`ae-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="ae-grid">
          {parts
            ? parts.map((part, i) => (
                <Thumb
                  key={part.name}
                  part={part}
                  color={value.color}
                  selected={value[tab as PartCategory] === i}
                  onSelect={() => setPart(tab as PartCategory, i)}
                />
              ))
            : COLORS.map((c) => (
                <button
                  type="button"
                  key={c.val}
                  className={`ae-color${value.color === c.val ? ' selected' : ''}`}
                  style={{ background: c.val }}
                  title={c.label}
                  onClick={() => setColor(c.val)}
                />
              ))}
        </div>
      </div>
    </div>
  );
}

export const AvatarEditor = memo(AvatarEditorInner);
export default AvatarEditor;
