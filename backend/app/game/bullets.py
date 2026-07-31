"""탄환 생성/시뮬레이션 (server/index.js 의 spawnBullet + 틱 루프 탄환 파트 포팅)."""

from __future__ import annotations

import math
import random
from typing import Any

from app.game import constants as C
from app.game.models import Bullet, Player, Room, Vec, Zone
from app.game.physics import (
    apply_explosion,
    bullet_hits_rect,
    clamp,
    entity_hit,
    handle_lethal,
)

# 소유자 카드에서 탄환으로 그대로 복사되는 플래그
_INHERITED_FLAGS = (
    "explosive", "supernova", "bombs_away", "decay", "remote", "drill_ammo",
    "ricochet", "chase", "fast_forward", "grow", "silence", "cold", "poison",
    "toxic_cloud", "target_bounce", "timed_detonation",
)

# 수명/도탄 소진 시 폭발하는 플래그
_BLAST_FLAGS = ("explosive", "supernova", "bombs_away", "timed_detonation")


def spawn_bullet(room: Room, player: Player, angle: float, **extra: Any) -> Bullet:
    """탄환 하나를 만들어 돌려준다(room 에 append 하지는 않는다).

    NOTE: PROTOCOL §5 는 `spawn_bullet(player, angle, **extra)` 로 적혀 있으나,
    Bullet.id 발급에 `room.next_bullet_id()` 가 필요하므로 room 을 첫 인자로 받는다.

    extra: speed_mult, damage_mult, spread, damage, knockback, life,
           size_bonus, max_bounces, pierce, explode_radius
    """
    speed_mult = player.bullet_speed_mult * float(extra.get("speed_mult", 1.0))
    base_speed = C.BASE_BULLET_SPEED * speed_mult

    shot_charge = clamp(player.windup, 0.0, C.MAX_CHARGE) / C.MAX_CHARGE
    careful = 1.2 if (player.has("careful_planning") and player.still_ticks >= 20) else 1.0
    wind_up = 1.0 + shot_charge * 0.75 if player.has("wind_up") else 1.0
    pristine = 1.2 if (player.has("pristine") and player.hp >= player.max_hp) else 1.0
    damage_mult = (
        player.damage_mult * float(extra.get("damage_mult", 1.0)) * careful * wind_up * pristine
    )

    spread = float(extra.get("spread", 0.0))
    if player.has("trickster"):
        spread += (random.random() - 0.5) * 0.16
    final_angle = angle + spread

    max_bounces = player.max_bounces + int(extra.get("max_bounces", 0))
    if player.has("target_bounce"):
        max_bounces += 1
    if player.has("ricochet"):
        max_bounces += 1

    vx = math.cos(final_angle) * base_speed
    vy = math.sin(final_angle) * base_speed
    if player.has("fast_forward"):
        vx *= 1.25
        vy *= 1.25

    flags: dict[str, Any] = {name: player.flags.get(name) for name in _INHERITED_FLAGS if player.has(name)}
    # 유도는 homing/chase/radar_shot 중 아무거나 있으면 켜진다
    if player.has("homing") or player.has("chase") or player.has("radar_shot"):
        flags["homing"] = True
    if player.has("radiance"):
        flags["radiance"] = True
    if player.has("decay"):
        flags["decay_rate"] = 0.985

    life = int(extra.get("life", 50 if player.has("fast_forward") else C.BASE_BULLET_LIFE))
    pierce = int(extra.get("pierce", 1 if player.has("drill_ammo") else 0))

    return Bullet(
        id=room.next_bullet_id(),
        owner=player.id,
        x=player.cx,
        y=player.cy,
        vx=vx,
        vy=vy,
        size=max(2.0, player.bullet_size + float(extra.get("size_bonus", 0.0))),
        color=str(player.customization.get("color", "#ffd43b")),
        damage=float(extra.get("damage", C.BASE_BULLET_DAMAGE)) * damage_mult,
        knockback=float(extra.get("knockback", C.BASE_KNOCKBACK)) * player.knockback_mult,
        life=life,
        max_bounces=max_bounces,
        pierce=pierce,
        explode_radius=float(extra.get("explode_radius", 85.0)),
        start_x=player.cx,
        start_y=player.cy,
        owner_aim=Vec(player.aim.x, player.aim.y),
        flags=flags,
    )


def _aim_angle(player: Player) -> float:
    return math.atan2(player.aim.y - player.cy, player.aim.x - player.cx)


def _pay_shot_costs(player: Player) -> None:
    if player.has("demonic_pact"):
        player.hp = max(1.0, player.hp - 2)
    if player.has("ritual_countdown"):
        player.windup = clamp(player.windup + 8, 0.0, C.MAX_CHARGE)


def fire(room: Room, player: Player) -> None:
    """일반 사격. buckshot/barrage/burst 산탄 계산 포함."""
    if player.hp <= 0 or player.silence_timer > 0 or player.cooldown > 0:
        return

    angle = _aim_angle(player)
    fire_count = player.buckshot + 1 if player.buckshot > 0 else (3 if player.has("barrage") else 1)
    burst_count = 3 if player.burst > 0 else 1
    total = fire_count * burst_count

    for i in range(total):
        spread = (i - (total - 1) / 2) * 0.08 if total > 1 else 0.0
        room.bullets.append(spawn_bullet(room, player, angle, spread=spread))

    _pay_shot_costs(player)
    player.cooldown = player.max_cooldown


def fire_strong(room: Room, player: Player) -> None:
    """강공격 릴리스. charge(0~60) 비례로 강화되고 STRONG_COOLDOWN 을 먹는다."""
    if player.hp <= 0 or player.silence_timer > 0 or not player.charging:
        return

    ratio = clamp(player.charge, 0.0, C.MAX_CHARGE) / C.MAX_CHARGE
    room.bullets.append(
        spawn_bullet(
            room,
            player,
            _aim_angle(player),
            damage_mult=1.0 + ratio * 0.6,
            size_bonus=2.0 + ratio * 4.0,
            damage=26.0 + ratio * 24.0,
            knockback=12.0 + ratio * 8.0,
            life=90,
            speed_mult=0.88 + ratio * 0.12,
        )
    )

    _pay_shot_costs(player)
    player.cooldown = C.STRONG_COOLDOWN
    player.charging = False
    player.charge = 0.0


# --- 틱 처리 ---------------------------------------------------------------


def _steer(room: Room, bullet: Bullet) -> None:
    """리모트 조종 + 최근접 적 유도."""
    if not (bullet.has("remote") or bullet.has("homing") or bullet.has("target_bounce")):
        return

    speed = math.hypot(bullet.vx, bullet.vy) or 1.0

    if bullet.has("remote"):
        owner = room.players.get(bullet.owner)
        aim = bullet.owner_aim if bullet.owner_aim else (owner.aim if owner else None)
        if aim is not None:
            tx = aim.x - bullet.x
            ty = aim.y - bullet.y
            dist = math.hypot(tx, ty) or 1.0
            steer = 0.08
            bullet.vx = bullet.vx * (1 - steer) + (tx / dist) * speed * steer
            bullet.vy = bullet.vy * (1 - steer) + (ty / dist) * speed * steer

    target = None
    closest = float("inf")
    for entity in room.entities():
        if entity.hp <= 0 or entity.id == bullet.owner:
            continue
        dist = math.hypot(entity.cx - bullet.x, entity.cy - bullet.y)
        if dist < closest:
            closest = dist
            target = entity

    if target is None:
        return
    tx = target.cx - bullet.x
    ty = target.cy - bullet.y
    dist = math.hypot(tx, ty) or 1.0
    speed = math.hypot(bullet.vx, bullet.vy) or 1.0
    steer = 0.08 if bullet.has("homing") else 0.05
    bullet.vx = bullet.vx * (1 - steer) + (tx / dist) * speed * steer
    bullet.vy = bullet.vy * (1 - steer) + (ty / dist) * speed * steer


def _detonate(room: Room, bullet: Bullet, damage: float, radius: float, knockback: float) -> None:
    apply_explosion(room, bullet.x, bullet.y, bullet.owner, damage, radius, knockback)


def _expire(room: Room, bullet: Bullet, damage_ratio: float) -> None:
    """수명/도탄 소진으로 탄환을 없앤다. 폭발 계열이면 터뜨린다."""
    if any(bullet.has(f) for f in _BLAST_FLAGS):
        _detonate(room, bullet, bullet.damage * damage_ratio, bullet.explode_radius, 16.0)
    bullet.active = False


def _bounce_walls(bullet: Bullet) -> None:
    if bullet.x < 0:
        bullet.x = 0.0
        bullet.vx *= -1
        bullet.bounces += 1
    elif bullet.x > C.WIDTH:
        bullet.x = C.WIDTH
        bullet.vx *= -1
        bullet.bounces += 1
    if bullet.y < 0:
        bullet.y = 0.0
        bullet.vy *= -1
        bullet.bounces += 1
    elif bullet.y > C.HEIGHT:
        bullet.y = C.HEIGHT
        bullet.vy *= -1
        bullet.bounces += 1


def _hit_platforms(room: Room, bullet: Bullet) -> None:
    for plat in room.platforms:
        if not bullet.active or not bullet_hits_rect(bullet, plat):
            continue
        prev_y = bullet.y - bullet.vy
        from_top_or_bottom = prev_y < plat["y"] or prev_y > plat["y"] + plat["height"]

        if bullet.max_bounces > 0 and bullet.bounces < bullet.max_bounces:
            if from_top_or_bottom:
                bullet.vy *= -1
            else:
                bullet.vx *= -1
            bullet.bounces += 1
            if bullet.has("target_bounce"):
                bullet.flags["homing"] = True
            if bullet.has("bombs_away"):
                _detonate(room, bullet, bullet.damage * 0.35, 70.0, 12.0)
        else:
            _expire(room, bullet, 0.7)
            return


def _consume(bullet: Bullet) -> None:
    """관통이 남았으면 1 깎고, 아니면 탄환을 소멸시킨다."""
    if bullet.has("drill_ammo") and bullet.pierce > 0:
        bullet.pierce -= 1
    else:
        bullet.active = False


def _reflect(room: Room, bullet: Bullet, player: Player) -> None:
    """가드 반사: 속도 반전 + 소유권 이전, echo 면 반격탄 1발."""
    previous_owner_id = bullet.owner
    bullet.vx *= -1.35
    bullet.vy *= -1.35
    bullet.owner = player.id
    bullet.owner_aim = Vec(player.aim.x, player.aim.y)
    bullet.bounces += 1

    if not player.has("echo") or player.echo_cooldown > 0:
        return
    player.echo_cooldown = 30
    attacker = room.players.get(previous_owner_id)
    if attacker is None:
        return
    angle = math.atan2(attacker.cy - player.cy, attacker.cx - player.cx)
    room.bullets.append(spawn_bullet(room, player, angle, damage_mult=0.65, speed_mult=1.1))


def _damage_player(room: Room, bullet: Bullet, player: Player) -> None:
    owner = room.players.get(bullet.owner)
    damage_mult = owner.damage_mult if owner else 1.0
    knockback_mult = owner.knockback_mult if owner else 1.0
    hit_damage = bullet.damage * damage_mult

    player.hp -= hit_damage
    player.vx += bullet.vx * 0.4 * knockback_mult
    player.vy -= 4

    # 상태이상
    poison_stacks = int(bullet.flags.get("poison", 0) or 0)
    if poison_stacks > 0:
        player.poison += 10 * poison_stacks
    if bullet.has("cold"):
        player.cold_timer = max(player.cold_timer, 60)
    if bullet.has("silence"):
        player.silence_timer = max(player.silence_timer, 60)

    # 소유자 보상
    if owner is not None:
        if owner.has("blood"):
            owner.blood_timer = 45
        if owner.lifesteal:
            owner.hp = min(owner.max_hp, owner.hp + hit_damage * owner.lifesteal)
        if owner.has("leech"):
            owner.hp = min(owner.max_hp, owner.hp + 2)
        if owner.has("scavenger"):
            owner.cooldown = max(0.0, owner.cooldown - 4)
        if owner.has("refresh"):
            owner.cooldown = max(0.0, owner.cooldown - 8)
        if owner.has("parasite"):
            owner.max_hp += 1
        if owner.has("radiance"):
            room.zones.append(Zone("radiance", bullet.x, bullet.y, 70.0, 8, bullet.owner))

    _spawn_hit_zones(room, bullet, hit_damage)
    if player.hp <= 0:
        handle_lethal(player)
    _consume(bullet)


def _spawn_hit_zones(room: Room, bullet: Bullet, hit_damage: float) -> None:
    if bullet.has("toxic_cloud"):
        room.zones.append(Zone("toxic", bullet.x, bullet.y, 75.0, 35, bullet.owner))
    if bullet.has("explosive") or bullet.has("supernova"):
        _detonate(room, bullet, hit_damage * 0.55, bullet.explode_radius, 16.0)


def _hit_players(room: Room, bullet: Bullet) -> None:
    for player in list(room.players.values()):
        if not bullet.active or player.hp <= 0 or bullet.owner == player.id:
            continue
        if not entity_hit(bullet, player):
            continue
        if player.blocking and player.block_meter > 0:
            _reflect(room, bullet, player)
        else:
            _damage_player(room, bullet, player)


def _hit_bots(room: Room, bullet: Bullet) -> None:
    from app.game import bots as bots_mod

    for bot in list(room.bots.values()):
        if not bullet.active or bot.hp <= 0 or bullet.owner == bot.id:
            continue
        if not entity_hit(bullet, bot):
            continue
        hit_damage = bullet.damage
        bot.hp -= hit_damage
        bot.vx += bullet.vx * 0.4
        bot.vy -= 4
        if bot.hp <= 0:
            bots_mod.respawn_bot(bot)
        _spawn_hit_zones(room, bullet, hit_damage)
        _consume(bullet)


def update_bullets(room: Room) -> None:
    """탄환 1틱: 조향 -> 이동 -> 수명/성장/감쇠 -> 벽/발판 -> 명중 -> 정리."""
    for bullet in list(room.bullets):
        if not bullet.active:
            continue

        _steer(room, bullet)

        bullet.x += bullet.vx
        bullet.y += bullet.vy
        bullet.life -= 1

        if bullet.has("grow"):
            bullet.damage += 0.05
            bullet.size += 0.01
        if bullet.has("decay"):
            rate = float(bullet.flags.get("decay_rate", 1.0))
            bullet.vx *= rate
            bullet.vy *= rate
            bullet.damage *= 0.99

        if bullet.life <= 0:
            _expire(room, bullet, 0.6)
            continue

        _bounce_walls(bullet)
        if bullet.bounces > bullet.max_bounces:
            _expire(room, bullet, 0.6)
            continue

        _hit_platforms(room, bullet)
        if not bullet.active:
            continue

        _hit_players(room, bullet)
        if bullet.active:
            _hit_bots(room, bullet)

    room.bullets = [b for b in room.bullets if b.active]
