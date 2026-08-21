"""탄환 생성/시뮬레이션 (server/index.js 의 spawnBullet + 틱 루프 탄환 파트 포팅)."""

from __future__ import annotations

import math
import random
from typing import Any

from app.game import constants as C
from app.game.models import Bot, Bullet, Player, Room, Vec, Zone
from app.game.physics import (
    apply_explosion,
    bullet_hits_rect,
    clamp,
    entity_hit,
    handle_lethal,
)
from app.game.stats import bullet_falloff

# 소유자 카드에서 탄환으로 그대로 복사되는 플래그
_INHERITED_FLAGS = (
    "explosive", "supernova", "bombs_away", "decay", "remote", "drill_ammo",
    "ricochet", "chase", "fast_forward", "grow", "silence", "cold", "poison",
    "toxic_cloud", "target_bounce", "timed_detonation", "dazzle", "steady_shot",
)

# 수명/도탄 소진 시 폭발하는 플래그
_BLAST_FLAGS = ("explosive", "supernova", "bombs_away", "timed_detonation")


def _weakest_enemy_ratio(room: Room, player: Player) -> float:
    """살아 있는 적 중 가장 약한 쪽의 체력 비율(0~1). 적이 없으면 1.0."""
    ratios = [
        e.hp / e.max_hp
        for e in room.entities()
        if e.id != player.id and e.alive and e.max_hp > 0
    ]
    return clamp(min(ratios), 0.0, 1.0) if ratios else 1.0


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
    # OVERPOWER: 상대가 약할수록 / DEMONIC PACT: 내가 약할수록 세진다.
    overpower = 1.0
    if player.has("overpower"):
        overpower = 1.0 + (1.0 - _weakest_enemy_ratio(room, player)) * C.OVERPOWER_MAX_BONUS
    demonic = 1.0
    if player.has("demonic_pact") and player.max_hp > 0:
        missing = clamp(1.0 - player.hp / player.max_hp, 0.0, 1.0)
        demonic = 1.0 + missing * C.DEMONIC_MAX_BONUS
    damage_mult = (
        player.damage_mult
        * float(extra.get("damage_mult", 1.0))
        * careful
        * wind_up
        * pristine
        * overpower
        * demonic
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
    # 유도는 homing/chase/radar_shot 중 아무거나 있으면 켜진다. 세기는 카드마다 다르다.
    steer = max(
        C.CHASE_STEER if player.has("chase") else 0.0,
        C.HOMING_STEER if player.has("homing") else 0.0,
        C.RADAR_STEER if player.has("radar_shot") else 0.0,
    )
    if steer > 0:
        flags["homing"] = True
        flags["homing_steer"] = steer
    if player.has("radiance"):
        flags["radiance"] = True
    if player.has("decay"):
        flags["decay_rate"] = 0.985

    life = int(extra.get("life", 50 if player.has("fast_forward") else C.BASE_BULLET_LIFE))
    if player.has("steady_shot"):
        life += C.STEADY_LIFE_BONUS
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


def spawn_bot_bullet(room: Room, bot: Bot, angle: float) -> Bullet:
    """훈련장 봇 탄환. 플레이어 카드 효과가 하나도 섞이지 않는 순수 탄환이다.

    플레이어 탄환보다 느리고(BOT_BULLET_SPEED) 약하다 — 보고 피할 수 있어야 훈련이 된다.
    """
    speed = C.BOT_BULLET_SPEED
    return Bullet(
        id=room.next_bullet_id(),
        owner=bot.id,
        x=bot.cx,
        y=bot.cy,
        vx=math.cos(angle) * speed,
        vy=math.sin(angle) * speed,
        size=C.BOT_BULLET_SIZE,
        color=str(bot.customization.get("color", "#ff8787")),
        damage=bot.trait("damage"),
        knockback=C.BOT_KNOCKBACK,
        life=C.BOT_BULLET_LIFE,
        start_x=bot.cx,
        start_y=bot.cy,
        owner_aim=Vec(bot.aim.x, bot.aim.y),
    )


def _aim_angle(player: Player) -> float:
    return math.atan2(player.aim.y - player.cy, player.aim.x - player.cx)


def _pay_shot_costs(player: Player) -> None:
    if player.has("demonic_pact"):
        player.hp = max(1.0, player.hp - 2)
    if player.has("ritual_countdown"):
        player.windup = clamp(player.windup + 8, 0.0, C.MAX_CHARGE)


def _volley(room: Room, player: Player, angle: float, damage_mult: float = 1.0) -> None:
    """한 번의 사격. buckshot/barrage 는 여기서 부채꼴로 퍼진다."""
    count = player.buckshot + 1 if player.buckshot > 0 else (3 if player.has("barrage") else 1)
    for i in range(count):
        spread = (i - (count - 1) / 2) * 0.08 if count > 1 else 0.0
        room.bullets.append(
            spawn_bullet(room, player, angle, spread=spread, damage_mult=damage_mult)
        )
    _record(room, "shots", count)


def fire(room: Room, player: Player) -> None:
    """일반 사격. BURST 는 여기서 나가지 않고 update_burst 가 이어서 쏜다."""
    if player.hp <= 0 or player.silence_timer > 0 or player.cooldown > 0:
        return

    angle = _aim_angle(player)
    # EMPOWER: 가드로 충전해 둔 한 발. 점사의 첫 발에만 실린다.
    boost = 1.0
    if player.empower_ready:
        boost = C.EMPOWER_MULT
        player.empower_ready = False
    _volley(room, player, angle, damage_mult=boost)

    # BURST: 퍼뜨리지 않고 "같은 방향으로" 시간차를 두고 더 쏜다.
    if player.burst > 0:
        player.burst_queue = player.burst
        player.burst_timer = C.BURST_INTERVAL
        player.burst_angle = angle

    _pay_shot_costs(player)  # 한 번 누른 것 = 한 번의 사격이므로 비용도 한 번만
    player.cooldown = player.max_cooldown


def update_burst(room: Room, player: Player) -> None:
    """예약된 점사를 1틱 진행시킨다(sim.update_player 가 매 틱 부른다)."""
    if player.burst_queue <= 0:
        return
    if player.hp <= 0 or player.silence_timer > 0:
        cancel_burst(player)
        return

    player.burst_timer -= 1
    if player.burst_timer > 0:
        return

    _volley(room, player, player.burst_angle)
    player.burst_queue -= 1
    player.burst_timer = C.BURST_INTERVAL


def cancel_burst(player: Player) -> None:
    player.burst_queue = 0
    player.burst_timer = 0


def fire_strong(room: Room, player: Player) -> None:
    """강공격 릴리스. charge(0~60) 비례로 강화되고 STRONG_COOLDOWN 을 먹는다."""
    if player.hp <= 0 or player.silence_timer > 0 or not player.charging:
        return

    ratio = clamp(player.charge, 0.0, C.MAX_CHARGE) / C.MAX_CHARGE
    empower = 1.0
    if player.empower_ready:
        empower = C.EMPOWER_MULT
        player.empower_ready = False
    room.bullets.append(
        spawn_bullet(
            room,
            player,
            _aim_angle(player),
            damage_mult=(1.0 + ratio * 0.6) * empower,
            size_bonus=2.0 + ratio * 4.0,
            damage=26.0 + ratio * 24.0,
            knockback=12.0 + ratio * 8.0,
            life=90,
            speed_mult=0.88 + ratio * 0.12,
        )
    )

    _record(room, "shots", 1)
    _pay_shot_costs(player)
    player.cooldown = C.STRONG_COOLDOWN
    player.charging = False
    player.charge = 0.0


def _record(room: Room, key: str, amount: float = 1) -> None:
    """훈련장 성적 집계. pvp 방에서는 no-op 이다."""
    from app.game import training  # 지연 import (순환 방지)

    training.record(room, key, amount)


# --- 틱 처리 ---------------------------------------------------------------


def _turn_toward(bullet: Bullet, tx: float, ty: float, steer: float) -> None:
    """탄환 속도를 (tx, ty) 쪽으로 steer 만큼 비튼다. 속력은 유지한다."""
    dx = tx - bullet.x
    dy = ty - bullet.y
    dist = math.hypot(dx, dy) or 1.0
    speed = math.hypot(bullet.vx, bullet.vy) or 1.0
    bullet.vx = bullet.vx * (1 - steer) + (dx / dist) * speed * steer
    bullet.vy = bullet.vy * (1 - steer) + (dy / dist) * speed * steer


def _steer(room: Room, bullet: Bullet) -> None:
    """리모트 조종(마우스 커서 실시간 추적) + 최근접 적 유도."""
    if not (bullet.has("remote") or bullet.has("homing")):
        return

    if bullet.has("remote"):
        # 주인이 살아 있으면 지금 커서를 좇는다. 주인이 죽거나 나가면 마지막
        # 커서 위치(owner_aim)에 그대로 머문다 — 갑자기 방향이 튀지 않게.
        owner = room.players.get(bullet.owner)
        if owner is not None and owner.alive:
            bullet.owner_aim.x = owner.aim.x
            bullet.owner_aim.y = owner.aim.y
        _turn_toward(bullet, bullet.owner_aim.x, bullet.owner_aim.y, C.REMOTE_STEER)

    if not bullet.has("homing"):
        return

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
    # 유도 세기는 카드마다 다르다(RADAR SHOT < HOMING < CHASE).
    _turn_toward(bullet, target.cx, target.cy, float(bullet.flags.get("homing_steer", C.HOMING_STEER)))


def _detonate(room: Room, bullet: Bullet, damage: float, radius: float, knockback: float) -> None:
    apply_explosion(room, bullet.x, bullet.y, bullet.owner, damage, radius, knockback)


def _expire(room: Room, bullet: Bullet, damage_ratio: float) -> None:
    """수명/도탄 소진으로 탄환을 없앤다. 폭발 계열이면 터뜨린다."""
    if any(bullet.has(f) for f in _BLAST_FLAGS):
        damage = bullet.damage * damage_ratio * bullet_falloff(bullet)
        _detonate(room, bullet, damage, bullet.explode_radius, 16.0)
    bullet.active = False


def _bounced(bullet: Bullet) -> None:
    """도탄 1회. 튕길 때마다 수명이 늘어난다(BOUNCE_LIFE_BONUS)."""
    bullet.bounces += 1
    bullet.life += C.BOUNCE_LIFE_BONUS


def _bounce_walls(bullet: Bullet) -> None:
    if bullet.x < 0:
        bullet.x = 0.0
        bullet.vx *= -1
        _bounced(bullet)
    elif bullet.x > C.WIDTH:
        bullet.x = C.WIDTH
        bullet.vx *= -1
        _bounced(bullet)
    if bullet.y < 0:
        bullet.y = 0.0
        bullet.vy *= -1
        _bounced(bullet)
    elif bullet.y > C.HEIGHT:
        bullet.y = C.HEIGHT
        bullet.vy *= -1
        _bounced(bullet)


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
            _bounced(bullet)
            if bullet.has("target_bounce"):
                bullet.flags["homing"] = True
                bullet.flags.setdefault("homing_steer", C.HOMING_STEER)
            if bullet.has("bombs_away"):
                damage = bullet.damage * 0.35 * bullet_falloff(bullet)
                _detonate(room, bullet, damage, 70.0, 12.0)
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
    attacker = room.players.get(previous_owner_id)

    # 가드 게이지는 여기서만 닳는다. 센 탄일수록 많이 깎는다.
    cost = bullet.damage * bullet_falloff(bullet) * C.BLOCK_COST_PER_DAMAGE
    if player.has("shields_up"):
        cost *= 0.75
    player.block_meter = max(0.0, player.block_meter - cost)
    bullet.vx *= -1.35
    bullet.vy *= -1.35
    bullet.owner = player.id
    bullet.owner_aim = Vec(player.aim.x, player.aim.y)
    # 반사는 도탄이 아니다. bounces 를 올리면 도탄 카드가 없는 탄(max_bounces=0)이
    # 되받아친 다음 틱에 그대로 꺼져서 가드 반사가 아무 의미가 없어진다.
    # 되돌아갈 만큼의 수명은 새로 준다.
    bullet.life = max(bullet.life, C.BASE_BULLET_LIFE)
    # 반사한 순간이 새 발사 지점이다(거리 감쇠 기준 재설정) + 위력은 반사한 쪽 배율로 환산.
    bullet.start_x, bullet.start_y = bullet.x, bullet.y
    if attacker is not None and attacker.damage_mult:
        bullet.damage *= player.damage_mult / attacker.damage_mult

    if not player.has("echo") or player.echo_cooldown > 0:
        return
    player.echo_cooldown = 30
    if attacker is None:
        return
    angle = math.atan2(attacker.cy - player.cy, attacker.cx - player.cx)
    room.bullets.append(spawn_bullet(room, player, angle, damage_mult=0.65, speed_mult=1.1))


def _apply_status(bullet: Bullet, target: Player | Bot) -> None:
    """적중 상태이상. 플레이어든 봇이든 똑같이 건다.

    봇에게 안 걸면 훈련장에서 SILENCE/COLD/POISON/DAZZLE 이 통째로 무효가 된다.
    """
    poison_stacks = int(bullet.flags.get("poison", 0) or 0)
    if poison_stacks > 0:
        target.poison += 10 * poison_stacks
    if bullet.has("cold"):
        target.cold_timer = max(target.cold_timer, 60)
    if bullet.has("silence"):
        target.silence_timer = max(target.silence_timer, 60)
    if bullet.has("dazzle"):
        target.dazzle_timer = max(target.dazzle_timer, C.DAZZLE_HIT_TICKS)


def _damage_player(room: Room, bullet: Bullet, player: Player) -> None:
    owner = room.players.get(bullet.owner)
    knockback_mult = owner.knockback_mult if owner else 1.0
    # 소유자 공격력 배율은 발사 시점에 이미 반영됐다. 여기선 거리 감쇠만 곱한다.
    hit_damage = bullet.damage * bullet_falloff(bullet)

    player.hp -= hit_damage
    player.vx += bullet.vx * 0.4 * knockback_mult
    player.vy -= 4

    _apply_status(bullet, player)

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

    _record(room, "damage_taken", hit_damage)
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

    # 봇끼리는 서로 쏘지 않는다. 셋이 난사하다 자기들끼리 정리되면 훈련이 안 된다.
    if bullet.owner in room.bots:
        return

    for bot in list(room.bots.values()):
        if not bullet.active or bot.hp <= 0 or bullet.owner == bot.id:
            continue
        if not entity_hit(bullet, bot):
            continue
        hit_damage = bullet.damage * bullet_falloff(bullet)
        bot.hp -= hit_damage
        bot.vx += bullet.vx * 0.4
        bot.vy -= 4
        _apply_status(bullet, bot)

        _record(room, "damage_dealt", hit_damage)
        # 명중률은 탄환 1발당 한 번만 센다(관통탄이 여러 번 세지 않도록).
        if not bullet.has("counted_hit"):
            bullet.flags["counted_hit"] = True
            _record(room, "hits", 1)

        if bot.hp <= 0:
            bots_mod.kill_bot(bot)
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
