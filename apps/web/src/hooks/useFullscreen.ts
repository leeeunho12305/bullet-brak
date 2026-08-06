// 인게임 전체화면 토글.
// 브라우저는 클릭 같은 사용자 제스처 안에서 호출된 요청만 전체화면을 허용한다 —
// 캔버스 구석의 버튼이 그 제스처 역할을 한다(자동 진입은 하지 않는다).
import { useCallback, useEffect, useState } from 'react';
import type { RefObject } from 'react';

type FsRequest = (options?: FullscreenOptions) => Promise<void> | void;
type FsExit = () => Promise<void> | void;

/** 사파리는 아직 접두사가 붙은 이름만 가지고 있다. */
interface FsElement extends HTMLElement {
  webkitRequestFullscreen?: FsRequest;
}
interface FsDocument extends Document {
  webkitFullscreenElement?: Element | null;
  webkitFullscreenEnabled?: boolean;
  webkitExitFullscreen?: FsExit;
}

function currentFsElement(): Element | null {
  const doc = document as FsDocument;
  return doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

/** iOS 사파리나 allow-fullscreen 이 없는 iframe 이면 false */
function fullscreenEnabled(): boolean {
  const doc = document as FsDocument;
  return doc.fullscreenEnabled ?? doc.webkitFullscreenEnabled ?? false;
}

function swallow(p: Promise<void> | void): void {
  // 거부(제스처 없음 등)는 조용히 넘긴다 — 버튼은 그대로 남아 있으니 다시 누르면 된다.
  if (p) void p.then(undefined, () => undefined);
}

export interface FullscreenControls {
  /** 지금 전체화면인가 */
  active: boolean;
  /** 이 브라우저에서 전체화면을 쓸 수 있는가 */
  supported: boolean;
  toggle(): void;
}

/** `ref` 가 가리키는 요소를 전체화면으로 넣었다 뺐다 한다. */
export function useFullscreen(ref: RefObject<HTMLElement | null>): FullscreenControls {
  const [active, setActive] = useState<boolean>(() => currentFsElement() !== null);
  const [supported] = useState<boolean>(fullscreenEnabled);

  useEffect(() => {
    const onChange = (): void => setActive(currentFsElement() !== null);
    document.addEventListener('fullscreenchange', onChange);
    document.addEventListener('webkitfullscreenchange', onChange);
    onChange();
    return () => {
      document.removeEventListener('fullscreenchange', onChange);
      document.removeEventListener('webkitfullscreenchange', onChange);
    };
  }, []);

  // 제스처 유효기간이 짧다 — 클릭 핸들러 안에서 동기로 호출해야 한다.
  const toggle = useCallback(() => {
    const doc = document as FsDocument;
    if (currentFsElement() !== null) {
      const exit: FsExit | undefined = doc.exitFullscreen ?? doc.webkitExitFullscreen;
      if (exit) swallow(exit.call(doc));
      return;
    }
    const el = ref.current;
    if (!el) return;
    const target = el as FsElement;
    const request: FsRequest | undefined = target.requestFullscreen ?? target.webkitRequestFullscreen;
    if (request) swallow(request.call(target, { navigationUI: 'hide' }));
  }, [ref]);

  return { active, supported, toggle };
}

export default useFullscreen;
