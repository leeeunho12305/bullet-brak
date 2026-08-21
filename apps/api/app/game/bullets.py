"""탄환 생성/시뮬레이션 (server/index.js 의 spawnBullet + 틱 루프 탄환 파트 포팅)."""

from __future__ import annotations

import math
import random
from typing import Any

from app.game import blocks
from app.game import constants as C
from app.game.models import Bot, Bullet, Player, Room, Vec, Zone
from app.game.physics import (
    apply_explosion,
    apply_knockback,
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

#: 유도 카드별 조향 세기(클수록 급하게 꺾는다). 여러 장이면 가장 센 것 하나만 쓴다.
_STEER_BY_CARD = (("chase", 0.14), ("homing", 0.08), ("radar_shot", 0.05))
#: TARGET BOUNCE 가 도탄한 뒤에 얻는 조향 세기(유도 카드가 없을 때의 기본값).
_BOUNCE_STEER = 0.06

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
    ritual = 1.0 + shot_charge * 0.5 if player.has("ritual_countdown") else 1.0
    pristine = 1.2 if (player.has("pristine") and player.hp >= player.max_hp) else 1.0
    pact = 1.35 if player.has("demonic_pact") else 1.0
    damage_mult = (
        player.damage_mult
        * float(extra.get("damage_mult", 1.0))
        * careful
        * wind_up
        * ritual
        * pristine
        * pact
        * _overpower_mult(room, player)
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
    # 유도는 homing/chase/radar_shot 중 아무거나 있으면 켜지고, 가장 센 조향을 쓴다.
    steer = next((value for card, value in _STEER_BY_CARD if player.has(card)), 0.0)
    if steer:
        flags["homing"] = True
        flags["steer"] = steer
    if player.has("radiance"):
        flags["radiance"] = True
    if player.has("decay"):
        flags["decay_rate"] = 0.985
    # 산탄 한 알. 감쇠 곡선이 따로다(stats.bullet_falloff) — 붙으면 세고 조금만 멀어져도 약하다.
    if extra.get("scatter"):
        flags["scatter"] = True

    life = int(extra.get("life", 50 if player.has("fast_forward") else C.BASE_BULLET_LIFE))
    if player.has("steady_shot"):
        life = int(life * 1.5)
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
        life_max=life,
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
        life_max=C.BOT_BULLET_LIFE,
        start_x=bot.cx,
        start_y=bot.cy,
        owner_aim=Vec(bot.aim.x, bot.aim.y),
    )


def _aim_angle(player: Player) -> float:
    return math.atan2(player.aim.y - player.cy, player.aim.x - player.cx)


def _overpower_mult(room: Room, player: Player) -> float:
    """OVERPOWER: 가장 약해진 적의 체력이 낮을수록 강해진다(빈사 상대에게 최대 ×1.5)."""
    if not player.has("overpower"):
        return 1.0
    ratios = [
        e.hp / e.max_hp
        for e in room.entities()
        if e.id != player.id and e.hp > 0 and e.max_hp > 0
    ]
    if not ratios:
        return 1.0
    return 1.0 + (1.0 - min(ratios)) * 0.5


def _take_empower(player: Player) -> float:
    """EMPOWER: 가드 직후 첫 사격 한 번만 강화된다(쓰면 바로 사라진다)."""
    if not player.empower_ready:
        return 1.0
    player.empower_ready = False
    return 1.6


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
    empower = _take_empower(player)
    scatter = player.buckshot > 0
    fire_count = player.buckshot + 1 if scatter else (3 if player.has("barrage") else 1)
    burst_count = 3 if player.burst > 0 else 1
    total = fire_count * burst_count

    for i in range(total):
        spread = (i - (total - 1) / 2) * 0.08 if total > 1 else 0.0
        room.bullets.append(
            spawn_bullet(room, player, angle, spread=spread, damage_mult=empower, scatter=scatter)
        )

    _record(room, "shots", total)
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
            damage_mult=(1.0 + ratio * 0.6) * _take_empower(player),
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


def _turn(bullet: Bullet, tx: float, ty: float, steer: float, speed: float) -> None:
    """탄환을 (tx, ty) 방향으로 `steer` 만큼 꺾되 속력은 그대로 둔다.

    두 벡터를 그냥 섞으면 많이 꺾일수록 합벡터가 짧아진다 — 적 코앞에서 크게 꺾이는
    유도탄이 눈에 띄게 느려지던 원인이다. 섞은 뒤 원래 속력으로 다시 늘여 준다.
    """
    dist = math.hypot(tx, ty) or 1.0
    vx = bullet.vx * (1 - steer) + (tx / dist) * speed * steer
    vy = bullet.vy * (1 - steer) + (ty / dist) * speed * steer
    scale = speed / (math.hypot(vx, vy) or 1.0)
    bullet.vx = vx * scale
    bullet.vy = vy * scale


def _steer(room: Room, bullet: Bullet) -> None:
    """리모트 조종 + 최근접 적 유도.

    TARGET BOUNCE 는 여기서 아무 일도 하지 않는다 — 벽이나 발판에 튕긴 순간
    `flags["homing"]` 이 붙고, 그때부터 아래 유도에 걸린다. 예전에는 `target_bounce`
    플래그만 보고 곧장 유도를 걸어서, 한 번도 튕기지 않은 탄이 적을 쫓아갔다.
    """
    homing = bullet.has("homing")
    if not (bullet.has("remote") or homing):
        return

    speed = math.hypot(bullet.vx, bullet.vy) or 1.0

    if bullet.has("remote"):
        # **지금** 조준하는 지점을 따라간다. `owner_aim` 은 발사(또는 반사) 시점의 사본이라
        # 소유자가 방을 나간 뒤에만 쓴다. 예전에는 사본을 먼저 봤기 때문에, 카드 설명과 달리
        # 탄이 "쏠 때 겨눴던 한 점"으로 빨려들어 그 자리를 맴돌았다 — 조종도 안 되고
        # 멀리 날아가지도 않으면서 남이 보기엔 유도탄처럼만 보이던 원인이다.
        owner = room.players.get(bullet.owner)
        aim = owner.aim if owner is not None else bullet.owner_aim
        if aim is not None:
            dx, dy = aim.x - bullet.x, aim.y - bullet.y
            # 조준점에 닿으면 더 꺾지 않는다. 안 그러면 커서 주위를 뱅뱅 돌기만 한다.
            if math.hypot(dx, dy) > C.REMOTE_DEADZONE:
                _turn(bullet, dx, dy, C.REMOTE_STEER, speed)

    if not homing:
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
    steer = float(bullet.flags.get("steer", _BOUNCE_STEER))
    _turn(bullet, target.cx - bullet.x, target.cy - bullet.y, steer, speed)


def _detonate(room: Room, bullet: Bullet, damage: float, radius: float, knockback: float) -> None:
    apply_explosion(room, bullet.x, bullet.y, bullet.owner, damage, radius, knockback)


def _expire(room: Room, bullet: Bullet, damage_ratio: float) -> None:
    """수명/도탄 소진으로 탄환을 없앤다. 폭발 계열이면 터뜨린다."""
    if any(bullet.has(f) for f in _BLAST_FLAGS):
        damage = bullet.damage * damage_ratio * bullet_falloff(bullet)
        _detonate(room, bullet, damage, bullet.explode_radius, 16.0)
    bullet.active = False


def _ricochet(bullet: Bullet, counted: bool = True) -> None:
    """튕긴 직후 처리: 도탄 카운트 + 사거리(수명) 초기화 + TARGET BOUNCE 추적 점화.

    수명을 되돌리는 게 핵심이다. 예전에는 튕겨도 수명이 계속 줄어서, 도탄을 다섯 장
    골라도 두세 번 튕기면 공중에서 사라졌다 — "도탄을 많이 골라도 많이 튕기질 못한다".
    """
    if bullet.has("target_bounce"):
        bullet.flags["homing"] = True
    if not counted:
        # 유도탄이 월드 경계에 부딪힌 경우다. 도탄으로도 세지 않고 수명도 되돌리지 않는다 —
        # 되돌리면 쫓을 적이 없을 때 벽 사이를 영원히 오가는 탄이 된다.
        return
    bullet.bounces += 1
    bullet.life = bullet.life_max


def _bounce_walls(bullet: Bullet) -> None:
    """월드 경계 처리.

    좌/우/천장은 실제 벽이다 — 플레이어도 여기서 막힌다(sim.update_player). 반면 **바닥은
    뚫려 있다**(낙사 구간). 예전에는 y > HEIGHT 에서도 튕겨서, 협곡·부유섬의 허공에서
    탄환이 아무것도 없는 자리에 부딪혀 되돌아왔다. 아래로 나간 탄은 그냥 사라진다.
    """
    # 유도탄은 벽을 뚫고 가므로 월드 경계도 도탄으로 세지 않는다. 그래야 일반 탄과
    # 똑같이 수명(life)만으로 사라진다.
    counted = not bullet.has("homing")
    if bullet.y > C.HEIGHT:
        bullet.active = False
        return

    hit = False
    if bullet.x < 0:
        bullet.x = 0.0
        bullet.vx *= -1
        hit = True
    elif bullet.x > C.WIDTH:
        bullet.x = C.WIDTH
        bullet.vx *= -1
        hit = True
    if bullet.y < 0:
        bullet.y = 0.0
        bullet.vy *= -1
        hit = True
    if hit:
        _ricochet(bullet, counted)


def _hit_platforms(room: Room, bullet: Bullet) -> None:
    for plat in room.platforms:
        if not bullet.active or not bullet_hits_rect(bullet, plat):
            continue
        if not blocks.is_solid(plat):
            continue  # 점프대는 실체가 없다 — 탄환도 그냥 지나간다
        prev_y = bullet.y - bullet.vy
        from_top_or_bottom = prev_y < plat["y"] or prev_y > plat["y"] + plat["height"]

        if bullet.max_bounces > 0 and bullet.bounces < bullet.max_bounces:
            if from_top_or_bottom:
                bullet.vy *= -1
            else:
                bullet.vx *= -1
            _ricochet(bullet)
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
    """가드 반사: 속도 반전 + 소유권 이전, echo 면 반격탄 1발.

    **반사는 도탄이 아니다.** 예전에는 여기서 `bounces` 를 올렸는데, 도탄 카드가 없는
    보통 탄환은 `max_bounces` 가 0 이라 다음 틱의 `bounces > max_bounces` 검사에 걸려
    곧바로 사라졌다 — 막아도 되돌아가는 탄이 안 보이던 이유다. 대신 수명만 되돌려서
    반사한 탄이 상대에게 닿을 때까지 날아가게 한다.
    """
    previous_owner_id = bullet.owner
    attacker = room.players.get(previous_owner_id)
    bullet.vx *= -1.35
    bullet.vy *= -1.35
    bullet.owner = player.id
    bullet.owner_aim = Vec(player.aim.x, player.aim.y)
    bullet.life = bullet.life_max
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


def _knock(bullet: Bullet, target: Player | Bot) -> None:
    """피격 넉백. 탄환이 날아온 방향으로 민다.

    예전에는 `vx += bullet.vx * 0.4` 였는데, 그 속도는 다음 틱에 이동 속도 clamp 와 마찰이
    지워 버려서 낙사 맵이 아니면 넉백에 아무 의미가 없었다. 이제 세기는 `Bullet.knockback`
    (= BASE_KNOCKBACK × 소유자 배율)에서 나오고, 이동 속도를 넘는 부분은 sim/bots 의 물리가
    천천히 식힌다(C.KNOCKBACK_DECAY). 위로 뜨는 양만 MAX_HIT_LIFT 로 묶는다.
    """
    apply_knockback(target, bullet.vx, bullet.vy, bullet.knockback * C.KNOCKBACK_SCALE)


def _damage_player(room: Room, bullet: Bullet, player: Player) -> None:
    owner = room.players.get(bullet.owner)
    # 소유자 공격력 배율은 발사 시점에 이미 반영됐다. 여기선 거리 감쇠만 곱한다.
    hit_damage = bullet.damage * bullet_falloff(bullet)

    player.hp -= hit_damage
    _knock(bullet, player)

    # 상태이상
    poison_stacks = int(bullet.flags.get("poison", 0) or 0)
    if poison_stacks > 0:
        player.poison += 10 * poison_stacks
    if bullet.has("cold"):
        player.cold_timer = max(player.cold_timer, 60)
    if bullet.has("silence"):
        player.silence_timer = max(player.silence_timer, 60)
    if bullet.has("dazzle"):
        player.dazzle_timer = max(player.dazzle_timer, 25)

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
            # 장판을 **쏜 사람 발밑**에 깐다. 예전에는 명중 지점(= 상대 위치)에 깔았는데,
            # radiance 는 소유자만 회복하는 장판이라(sim.OWNER_ONLY_ZONES) 상대 발밑에
            # 깔리면 회복은 한 번도 안 되면서 화면에는 "상대가 회복 장판을 밟고 있는" 그림만
            # 남았다 — 회복 장판이 적을 살려 준다는 오해의 출처다.
            room.zones.append(Zone("radiance", owner.cx, owner.cy, 70.0, 8, owner.id))

    _record(room, "damage_taken", hit_damage)
    _spawn_hit_zones(room, bullet, hit_damage)
    if player.hp <= 0:
        handle_lethal(player)
    _consume(bullet)


def _spawn_hit_zones(room: Room, bullet: Bullet, hit_damage: float) -> None:
    if bullet.has("toxic_cloud"):
        room.zones.append(
            Zone("toxic", bullet.x, bullet.y, C.TOXIC_RADIUS, C.TOXIC_TICKS, bullet.owner)
        )
    if bullet.has("explosive") or bullet.has("supernova"):
        _detonate(room, bullet, hit_damage * 0.55, bullet.explode_radius, 16.0)


def _hit_players(room: Room, bullet: Bullet) -> None:
    for player in list(room.players.values()):
        if not bullet.active or player.hp <= 0 or bullet.owner == player.id:
            continue
        if not entity_hit(bullet, player):
            continue
        if player.blocking:
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
        _knock(bullet, bot)

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
        if not bullet.active:
            continue  # 열린 아래쪽으로 빠져나갔다 — 허공에서 터뜨릴 것도 없다
        if bullet.bounces > bullet.max_bounces:
            _expire(room, bullet, 0.6)
            continue

        # 유도탄은 벽을 뚫는다. 적을 쫓다 지형에 부딪혀 먼저 사라지면 "유도"가 아니라
        # 곡선으로 날아가는 일반 탄이 된다.
        if not bullet.has("homing"):
            _hit_platforms(room, bullet)
        if not bullet.active:
            continue

        _hit_players(room, bullet)
        if bullet.active:
            _hit_bots(room, bullet)

    room.bullets = [b for b in room.bullets if b.active]
