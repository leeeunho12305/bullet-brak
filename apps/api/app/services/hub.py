"""방별 WebSocket 연결 관리 + 브로드캐스트.

끊긴 소켓에 대한 send 는 예외를 삼키고 목록에서 제거한다(틱 루프가 죽으면 안 됨).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        # room_code -> {player_id: WebSocket}
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    # -- 등록 --------------------------------------------------------------
    def add(self, code: str, player_id: str, ws: WebSocket) -> None:
        self._rooms.setdefault(code, {})[player_id] = ws

    def remove(self, code: str, player_id: str) -> None:
        conns = self._rooms.get(code)
        if not conns:
            return
        conns.pop(player_id, None)
        if not conns:
            self._rooms.pop(code, None)

    def drop_room(self, code: str) -> None:
        self._rooms.pop(code, None)

    def count(self, code: str) -> int:
        return len(self._rooms.get(code, {}))

    def sockets(self, code: str) -> list[tuple[str, WebSocket]]:
        return list(self._rooms.get(code, {}).items())

    # -- 전송 --------------------------------------------------------------
    @staticmethod
    def _connected(ws: WebSocket) -> bool:
        return ws.client_state == WebSocketState.CONNECTED

    async def send(self, ws: WebSocket, payload: dict[str, Any]) -> bool:
        """단일 소켓 전송. 실패해도 예외를 올리지 않는다."""
        if not self._connected(ws):
            return False
        try:
            await ws.send_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
            return True
        except Exception:
            return False

    async def broadcast_text(self, code: str, text: str) -> None:
        """이미 직렬화된 문자열을 방 전체에 전송(스냅샷용 — dumps 1회)."""
        targets = self.sockets(code)
        if not targets:
            return
        results = await asyncio.gather(
            *(self._send_text(ws, text) for _, ws in targets), return_exceptions=True
        )
        for (player_id, _), ok in zip(targets, results):
            if ok is not True:
                self.remove(code, player_id)

    async def broadcast(self, code: str, payload: dict[str, Any]) -> None:
        await self.broadcast_text(
            code, json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        )

    async def _send_text(self, ws: WebSocket, text: str) -> bool:
        if not self._connected(ws):
            return False
        try:
            await ws.send_text(text)
            return True
        except Exception:
            return False


#: 프로세스 전역 싱글턴
hub = Hub()
