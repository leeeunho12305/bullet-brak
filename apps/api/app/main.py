"""FastAPI 진입점. 60Hz 틱 루프를 lifespan 에서 하나만 돌린다."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.ws import router as ws_router
from app.config import get_settings
from app.game import constants as C
from app.game import engine
from app.game.rooms import room_manager
from app.game.serialize import room_state, snapshot
from app.services.hub import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bullet-brak")

#: 방 코드 -> 직전 틱의 phase (페이즈 전환 이벤트 감지용)
_last_phase: dict[str, str] = {}

#: 방 코드 -> 직전 틱의 active_map_id. 맵이 바뀌면 room_state 를 한 번 더 쏜다.
#: (테마·맵 이름은 스냅샷에 매 틱 싣기엔 무거워서 저빈도 메시지로만 내려간다)
_last_map: dict[str, str] = {}

#: 빈 방 정리 주기(틱)
CLEANUP_PERIOD = 600
#: 드리프트가 이보다 크면 따라잡기를 포기하고 기준 시각을 재설정
MAX_DRIFT_SEC = 0.25


async def _tick_once(code: str) -> None:
    room = room_manager.get(code)
    if room is None:
        return
    # 첫 틱 이전에 phase 가 바뀌었을 수 있으므로 기본값은 "waiting"
    prev_phase = _last_phase.get(code, "waiting")
    engine.tick_room(room)
    _last_phase[code] = room.phase

    if _last_map.get(code) != room.active_map_id:
        _last_map[code] = room.active_map_id
        await hub.broadcast(code, {"type": "room_state", "room": room_state(room)})

    text = json.dumps(snapshot(room), separators=(",", ":"), ensure_ascii=False)
    await hub.broadcast_text(code, text)

    event = engine.phase_event(room, prev_phase)
    if event is not None:
        await hub.broadcast(code, event)


def _sweep() -> None:
    """플레이어가 없는 방과 남은 캐시를 정리."""
    for code in room_manager.cleanup_empty():
        hub.drop_room(code)
    for code in [c for c in _last_phase if c not in room_manager.rooms]:
        _last_phase.pop(code, None)
    for code in [c for c in _last_map if c not in room_manager.rooms]:
        _last_map.pop(code, None)


async def game_loop() -> None:
    """모든 방을 1/60초마다 시뮬레이션하고 스냅샷을 브로드캐스트한다."""
    target = time.perf_counter()
    ticks = 0
    logger.info("game loop 시작 (%dHz)", C.TICK_RATE)
    while True:
        target += C.TICK_SECONDS
        ticks += 1

        for code in list(room_manager.rooms.keys()):
            try:
                await _tick_once(code)
            except Exception:  # 방 하나가 터져도 루프는 계속
                logger.exception("tick 실패 (room=%s)", code)

        if ticks % CLEANUP_PERIOD == 0:
            try:
                _sweep()
            except Exception:
                logger.exception("빈 방 정리 실패")

        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            if delay < -MAX_DRIFT_SEC:  # 너무 밀렸으면 기준 시각 재설정
                target = time.perf_counter()
            await asyncio.sleep(0)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(game_loop(), name="game-loop")
    app.state.game_loop = task
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("game loop 종료")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
