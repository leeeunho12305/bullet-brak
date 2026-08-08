"""대미지 감쇠 계산과 HUD 용 스탯 요약.

렌더링/전송 레이어가 아니라 여기서 계산한다. 클라이언트에 숫자를 두 벌 두면
밸런스를 고칠 때마다 표가 거짓말을 하기 때문이다.
"""

from __future__ import annotations

import math

from app.game import constants as C
from app.game.models import Bullet, Player


def falloff_at(distance: float) -> float:
    """이동 거리에 따른 대미지 배율. 0px -> 1.5배, 600px 이상 -> 0.4배 (선형)."""
    t = min(max(distance, 0.0) / C.DAMAGE_FALLOFF_RANGE, 1.0)
    return C.DAMAGE_CLOSE_MULT + (C.DAMAGE_FAR_MULT - C.DAMAGE_CLOSE_MULT) * t


def bullet_falloff(bullet: Bullet) -> float:
    """탄환이 발사 지점에서 지금까지 날아온 거리 기준 배율.

    STEADY SHOT 은 이 감쇠를 절반만 받는다 — 근접에서 덜 세지는 대신 멀리서도 덜 약해진다.
    """
    mult = falloff_at(math.hypot(bullet.x - bullet.start_x, bullet.y - bullet.start_y))
    if bullet.has("steady_shot"):
        return 1.0 + (mult - 1.0) * 0.5
    return mult


def base_shot_damage(player: Player) -> float:
    """조건부 보너스(차징/정지/만피)를 뺀, 이 플레이어의 기본 사격 1발 위력."""
    return C.BASE_BULLET_DAMAGE * player.damage_mult


def damage_table(player: Player) -> list[dict[str, float]]:
    """Tab 오버레이용 거리별 대미지 표."""
    base = base_shot_damage(player)
    return [
        {"distance": float(d), "damage": round(base * falloff_at(d), 1)}
        for d in C.DAMAGE_TABLE_DISTANCES
    ]


def stat_summary(player: Player) -> dict[str, float]:
    """Tab 오버레이용 내 스탯 요약. 소수 둘째 자리에서 반올림."""
    shots = player.buckshot + 1 if player.buckshot else (3 if player.has("barrage") else 1)
    return {
        "damage_mult": round(player.damage_mult, 2),
        "max_hp": round(player.max_hp, 1),
        "speed": round(player.speed, 2),
        "cooldown": round(player.max_cooldown, 1),
        "bullet_speed": round(C.BASE_BULLET_SPEED * player.bullet_speed_mult, 2),
        "bullet_size": round(player.bullet_size, 1),
        "bounces": float(player.max_bounces),
        "knockback": round(player.knockback_mult, 2),
        "block_meter": round(player.block_meter_max, 1),
        "block_seconds": round(
            player.block_meter_max / max(1e-6, player.block_drain) / C.TICK_RATE, 1
        ),
        "shots_per_fire": float(shots * (3 if player.burst else 1)),
    }
