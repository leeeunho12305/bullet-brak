"""아주 작은 인메모리 레이트리미터.

인계 코드 입력처럼 **맞히면 계정이 통째로 넘어가는 창구**를 지키는 용도다.
코드 자체는 60비트라 무차별 대입으로 뚫리지 않지만, 시도를 무제한으로 열어 두면
로그와 DB 조회가 공짜 샌드백이 된다.

인스턴스 1대 전제(docs/DEPLOYMENT.md §2)라 프로세스 메모리로 충분하다. 가로 확장
(Phase 3)에 들어가면 Redis 로 옮겨야 한다 — 그때는 이 모듈만 갈아 끼우면 된다.
"""

from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """키별 슬라이딩 윈도우. `hit()` 이 False 면 한도를 넘긴 것이다."""

    def __init__(self, limit: int, window_sec: float, max_keys: int = 4096) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """시도를 한 번 기록한다. 허용되면 True, 한도 초과면 False.

        한도를 넘긴 시도도 창에 남긴다 — 그래야 두들길수록 문이 더 오래 닫힌다.
        """
        now = time.monotonic()
        window = self._hits.get(key)
        if window is None:
            self._sweep(now)
            window = self._hits.setdefault(key, deque())

        cutoff = now - self.window_sec
        while window and window[0] <= cutoff:
            window.popleft()

        window.append(now)
        return len(window) <= self.limit

    def retry_after(self, key: str) -> int:
        """지금 막혀 있다면 몇 초 뒤에 다시 열리는지(올림). 안 막혀 있으면 0."""
        window = self._hits.get(key)
        if not window or len(window) <= self.limit:
            return 0
        return max(1, int(self.window_sec - (time.monotonic() - window[0])) + 1)

    def reset(self, key: str | None = None) -> None:
        """테스트/운영용. 키를 주면 그 키만, 없으면 전부 지운다."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    def _sweep(self, now: float) -> None:
        """키가 너무 불어나면(=IP 를 갈아 가며 두들기면) 만료된 것부터 버린다."""
        if len(self._hits) < self.max_keys:
            return
        cutoff = now - self.window_sec
        for key in [k for k, w in self._hits.items() if not w or w[-1] <= cutoff]:
            self._hits.pop(key, None)
        # 그래도 가득이면(전부 살아 있는 창) 통째로 비운다. 정확도보다 상한이 중요하다.
        if len(self._hits) >= self.max_keys:
            self._hits.clear()
