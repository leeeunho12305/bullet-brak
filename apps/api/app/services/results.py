"""매치 결과를 틱 루프 밖으로 꺼내는 다리.

틱 루프는 결과를 **값으로 복사**해서 여기 던지기만 하고 곧바로 다음 프레임으로 간다
(`capture_*` 는 동기 함수다). DB 쓰기와 알림은 별도 태스크에서 돈다 — 60Hz 안에
`await db` 가 끼면 그 프레임이 통째로 밀린다.

기록에 실패해도 게임은 아무 영향을 받지 않는다. DB 가 없거나 죽어 있으면 그냥
아무것도 남지 않고 매치는 평소처럼 끝난다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.db import db_ready, session_scope
from app.game.models import Player, Room
from app.services import matches
from app.services.hub import hub

logger = logging.getLogger(__name__)

#: 진행 중인 기록 태스크. 참조를 들고 있지 않으면 GC 가 도중에 수거할 수 있다.
_tasks: set[asyncio.Task[None]] = set()


def _participants(
    room: Room, players: list[Player], winner_id: str | None
) -> list[matches.ParticipantResult]:
    return [
        matches.ParticipantResult(
            slot=slot,
            player_id=p.id,
            account_id=p.account_id,
            nickname=p.nickname or "익명",
            score=int(room.scores.get(p.id, 0)),
            won=p.id == winner_id,
            coins_earned=max(0, int(p.coins_earned)),
        )
        for slot, p in enumerate(players)
    ]


def _duration(room: Room) -> int:
    if room.started_at <= 0.0:
        return 0
    return max(0, int(time.monotonic() - room.started_at))


def capture_finish(room: Room) -> matches.MatchOutcome | None:
    """정상 종료(phase 가 finished 로 넘어간 순간)의 결과. 훈련장은 기록하지 않는다."""
    if room.mode != "pvp" or not room.players:
        return None
    players = list(room.players.values())
    return matches.MatchOutcome(
        room_code=room.code,
        mode=room.mode,
        ranked=room.ranked,
        map_id=room.active_map_id,
        rounds=room.rounds_played,
        duration_sec=_duration(room),
        forfeit=False,
        participants=_participants(room, players, room.winner_id),
    )


def capture_forfeit(room: Room, leaver: Player) -> matches.MatchOutcome | None:
    """경쟁전 도중 이탈. 남은 사람이 이긴 것으로 기록한다.

    이게 없으면 "질 것 같으면 나간다"가 최적 전략이 된다. 나간 쪽은 그 판을 진 것으로
    치고 RR 을 잃는다 — 발로란트의 탈주 처리와 같은 뜻이다.

    ⚠ **`leaver` 는 이미 `room.players` 에서 빠진 뒤에 넘어온다.** 그래서 참가자 목록을
      여기서 다시 합쳐 준다.
    """
    if not room.ranked or room.mode != "pvp":
        return None
    remaining = list(room.players.values())
    if len(remaining) != 1:
        # 1:1 이 아니었거나 둘 다 나갔다. 승자를 정할 수 없으면 기록하지 않는다.
        return None

    winner = remaining[0]
    return matches.MatchOutcome(
        room_code=room.code,
        mode=room.mode,
        ranked=True,
        map_id=room.active_map_id,
        rounds=room.rounds_played,
        duration_sec=_duration(room),
        forfeit=True,
        participants=_participants(room, [winner, leaver], winner.id),
    )


def schedule(outcome: matches.MatchOutcome | None) -> None:
    """결과를 백그라운드에서 기록한다. 호출부는 기다리지 않는다."""
    if outcome is None or not db_ready():
        return
    task = asyncio.create_task(_persist(outcome), name=f"match-record-{outcome.room_code}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _persist(outcome: matches.MatchOutcome) -> None:
    """DB 에 저장하고, 랭크가 걸린 판이면 방에 결과를 알린다."""
    try:
        async with session_scope() as session:
            changes = await matches.record(session, outcome)
    except Exception:
        # 기록 실패로 게임이 멈추면 안 된다. 로그만 남기고 조용히 지나간다.
        logger.exception("매치 기록 실패 (room=%s)", outcome.room_code)
        return

    if not changes:
        return
    await _notify(outcome.room_code, changes)


async def _notify(code: str, changes: dict[str, dict[str, Any]]) -> None:
    """`rank_update` 브로드캐스트.

    자기 변동만 필요하지만 방에 둘뿐이라 통째로 보낸다 — 상대가 얼마나 올랐는지
    보이는 편이 경쟁전답고, 어차피 리더보드에 공개되는 값이다.
    """
    try:
        await hub.broadcast(code, {"type": "rank_update", "changes": changes})
    except Exception:
        logger.exception("rank_update 전송 실패 (room=%s)", code)
