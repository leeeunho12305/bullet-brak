"""충돌/폭발 등 순수 물리 헬퍼 (server/index.js 의 checkCollision / applyExplosion 포팅)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:  # 순환 import 방지 (런타임에는 필요 없음)
    from app.game.models import Bot, Player, Room

Entity = Union["Player", "Bot"]
Rect = dict


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def resolve_platform_collision(entity: Entity, rect: Rect) -> None:
    """AABB 최소 관통축 밀어내기. 착지하면 grounded=True, Player 면 jumps=0."""
    ex, ey = entity.x, entity.y
    ew, eh = entity.width, entity.height
    rx, ry = float(rect["x"]), float(rect["y"])
    rw, rh = float(rect["width"]), float(rect["height"])

    if not (ex < rx + rw and ex + ew > rx and ey < ry + rh and ey + eh > ry):
        return

    overlap_bottom = ey + eh - ry
    overlap_top = ry + rh - ey
    overlap_right = ex + ew - rx
    overlap_left = rx + rw - ex

    smallest = min(
        overlap_bottom,
        max(0.0, overlap_top),
        max(0.0, overlap_right),
        max(0.0, overlap_left),
    )

    if smallest == overlap_bottom and entity.vy > 0:
        entity.y = ry - eh
        entity.vy = 0.0
        entity.grounded = True
        if hasattr(entity, "jumps"):
            entity.jumps = 0
    elif smallest == overlap_top and entity.vy < 0:
        entity.y = ry + rh
        entity.vy = 0.0
    elif smallest == overlap_right:
        entity.x = rx - ew
        entity.vx = 0.0
    elif smallest == overlap_left:
        entity.x = rx + rw
        entity.vx = 0.0


def bullet_hits_rect(bullet, rect: Rect) -> bool:
    """탄환(점)이 사각형 내부에 있는지."""
    return (
        bullet.x >= rect["x"]
        and bullet.x <= rect["x"] + rect["width"]
        and bullet.y >= rect["y"]
        and bullet.y <= rect["y"] + rect["height"]
    )


def entity_hit(bullet, entity: Entity) -> bool:
    """탄환이 엔티티 히트박스 안에 있는지(경계 제외 — JS 와 동일)."""
    return (
        bullet.x > entity.x
        and bullet.x < entity.x + entity.width
        and bullet.y > entity.y
        and bullet.y < entity.y + entity.height
    )


def entities_in_radius(
    room: "Room", x: float, y: float, radius: float
) -> list[tuple[Entity, float, float, float]]:
    """반경 안의 살아있는 엔티티를 (entity, distance, dx, dy) 로 돌려준다.

    dx/dy 는 중심 -> 엔티티 방향. distance == 0 인 경우는 방향을 못 정하므로 제외.
    """
    found: list[tuple[Entity, float, float, float]] = []
    for target in room.entities():
        if target.hp <= 0:
            continue
        dx = target.cx - x
        dy = target.cy - y
        distance = math.hypot(dx, dy)
        if distance > radius or distance == 0:
            continue
        found.append((target, distance, dx, dy))
    return found


def handle_lethal(player: "Player") -> None:
    """hp<=0 인 플레이어 처리. revives 가 남았으면 부활, 아니면 상태만 정리.

    라운드 판정은 engine 담당이므로 여기서는 hp 를 0 이하로 둔 채 두기만 한다.
    """
    if player.hp > 0:
        return
    if player.revives > 0:
        player.revives -= 1
        player.hp = player.max_hp
        return
    player.vx = 0.0
    player.vy = 0.0
    player.blocking = False
    player.charging = False
    player.charge = 0.0
    player.block_meter = 0.0
    player.silence_timer = 0
    player.poison = 0


def apply_explosion(
    room: "Room",
    x: float,
    y: float,
    owner_id: str,
    damage: float,
    radius: float = 90.0,
    knockback: float = 14.0,
) -> None:
    """거리 감쇠 폭발 피해 + 넉백을 플레이어/봇 모두에 적용한다."""
    from app.game import bots as bots_mod  # 순환 import 회피

    for target, distance, dx, dy in entities_in_radius(room, x, y, radius):
        power = 1.0 - distance / radius
        target.hp -= damage * power
        target.vx += (dx / distance) * knockback * power
        target.vy += (dy / distance) * knockback * power
        if target.hp > 0:
            continue
        if target.id in room.bots:
            bots_mod.kill_bot(target)  # type: ignore[arg-type]
        else:
            handle_lethal(target)  # type: ignore[arg-type]
