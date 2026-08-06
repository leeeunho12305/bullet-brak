"""카드 정의와 적용 로직 (server/index.js 의 CARDS 배열 포팅).

- 불리언 효과는 `player.flags[key] = True` 로 저장한다.
  키는 JS 필드명에서 `Card` 접미사를 뗀 snake_case (`homingCard` -> `"homing"`).
- 실제 스탯(damage_mult, max_hp, ...)은 flags 가 아니라 Player 필드를 직접 바꾼다.
- `flags["poison"]` 은 "내가 쏜 탄환이 거는 독 스택"(누적 카운트)이고,
  `player.poison` 은 "지금 내가 걸린 독"이다. 혼동 주의.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable

from app.game import constants as C
from app.game.models import Player


@dataclass
class Card:
    id: str
    name: str
    desc: str
    category: str  # attack|survival|utility|movement|special
    color: str
    emoji: str
    apply: Callable[[Player], None]


# --- 효과 헬퍼 -------------------------------------------------------------


def _flag(name: str, amount: Any = True) -> Callable[[Player], None]:
    """불리언 플래그를 세우거나(amount=True) 숫자를 누적한다."""

    def apply(p: Player) -> None:
        if amount is True:
            p.flags[name] = True
        else:
            p.flags[name] = p.flags.get(name, 0) + amount

    return apply


def _add(**deltas: float) -> Callable[[Player], None]:
    """Player 필드에 델타를 더한다."""

    def apply(p: Player) -> None:
        for key, delta in deltas.items():
            setattr(p, key, getattr(p, key) + delta)

    return apply


# --- 복합 효과 -------------------------------------------------------------


def _mayhem(p: Player) -> None:
    p.max_bounces += 5
    p.damage_mult *= 0.85


def _quick_reload(p: Player) -> None:
    p.max_cooldown = max(2.0, p.max_cooldown - 5)


def _quick_shot(p: Player) -> None:
    p.max_cooldown = max(2.0, p.max_cooldown - 7)


def _spray(p: Player) -> None:
    p.max_cooldown = 3.0
    p.damage_mult *= 0.3


def _sneaky(p: Player) -> None:
    p.flags["sneaky"] = True
    p.bullet_speed_mult += 0.15
    p.bullet_size = max(2.0, p.bullet_size - 1)


def _shields_up(p: Player) -> None:
    p.flags["shields_up"] = True
    p.block_meter_max = max(300.0, p.block_meter_max + 150)
    p.block_meter = p.block_meter_max


def _defender(p: Player) -> None:
    p.max_hp += 30
    p.hp += 30
    p.block_meter_max = max(300.0, p.block_meter_max + 120)
    p.block_meter = p.block_meter_max


def _combine(p: Player) -> None:
    p.damage_mult *= 3.0
    p.max_cooldown *= 3.0


def _glass_cannon(p: Player) -> None:
    p.damage_mult += 1.0
    p.max_hp = max(1.0, float(math.floor(p.max_hp / 2)))
    p.hp = min(p.hp, p.max_hp)


def _huge(p: Player) -> None:
    p.width *= 1.5
    p.height *= 1.5
    p.bullet_size += 10


def _ricochet(p: Player) -> None:
    p.max_bounces += 1
    p.flags["ricochet"] = True


def _fast_forward(p: Player) -> None:
    p.flags["fast_forward"] = True
    p.bullet_speed_mult += 0.4


# --- 카드 목록 (JS CARDS 순서 유지) ----------------------------------------

CARDS: list[Card] = [
    Card('empower', 'EMPOWER', 'Your next shot is charged after a block', 'special', '#fcc419', '✨', _flag('empower')),
    Card('radiance', 'RADIANCE', 'Blocking sends out a wave of light', 'special', '#ffd43b', '🌟', _flag('radiance')),
    Card('scavenger', 'SCAVENGER', 'Dealing damage reloads you faster', 'utility', '#845ef7', '🧲', _flag('scavenger')),
    Card('poison', 'POISON', 'Hits stack poison on the target', 'attack', '#2f9e44', '☠️', _flag('poison', 1)),
    Card('mayhem', 'MAYHEM', 'More ricochets and wilder bullets', 'utility', '#d9480f', '💥', _mayhem),
    Card('bombs_away', 'BOMBS AWAY', 'Ricocheted bullets explode', 'attack', '#fa5252', '💣', _flag('bombs_away')),
    Card('pristine_persistence', 'PRISTINE PERSISTENCE', 'Stronger while at full health', 'survival', '#4dabf7', '🫧', _flag('pristine')),
    Card('phoenix', 'PHOENIX', 'Come back to life once', 'survival', '#f76707', '🐦‍🔥', _add(revives=1)),
    Card('quick_reload', 'QUICK RELOAD', 'Shorter cooldown between shots', 'attack', '#74c0fc', '🔫', _quick_reload),
    Card('grow', 'GROW', 'Bullets grow and hit harder as they travel', 'attack', '#ffd43b', '🌱', _flag('grow')),
    Card('supernova', 'SUPERNOVA', 'Bullets leave a small blast when they die', 'attack', '#ff922b', '🌟', _flag('supernova')),
    Card('spray', 'SPRAY', 'Faster fire rate, weaker per shot', 'attack', '#4dabf7', '🚿', _spray),
    Card('trickster', 'TRICKSTER', 'Shots veer slightly, harder to read', 'utility', '#f06595', '🃏', _flag('trickster')),
    Card('target_bounce', 'TARGET BOUNCE', 'Bouncing bullets seek the next target', 'utility', '#20c997', '🎯', _flag('target_bounce')),
    Card('timed_detonation', 'TIMED DETONATION', 'Bullets explode after a delay', 'attack', '#fd7e14', '⏱️', _flag('timed_detonation')),
    Card('sneaky', 'SNEAKY', 'Small, fast bullets that slip through', 'utility', '#adb5bd', '🥷', _sneaky),
    Card('homing', 'HOMING', 'Bullets track the nearest enemy', 'utility', '#bac8ff', '🧲', _flag('homing')),
    Card('silence', 'SILENCE', 'Hits briefly stop the target from firing', 'utility', '#9775fa', '🔇', _flag('silence')),
    Card('taste_of_blood', 'TASTE OF BLOOD', 'Dealing damage briefly boosts your speed', 'utility', '#c92a2a', '🩸', _flag('blood')),
    Card('toxic_cloud', 'TOXIC CLOUD', 'Hits leave a poison cloud behind', 'attack', '#40c057', '☁️', _flag('toxic_cloud')),
    Card('echo', 'ECHO', 'Blocking fires one extra counter shot', 'utility', '#339af0', '📣', _flag('echo')),
    Card('shield_charge', 'SHIELD CHARGE', 'Charge forward while blocking', 'utility', '#228be6', '🛡️', _flag('shield_charge')),
    Card('tactical_reload', 'TACTICAL RELOAD', 'Blocking cuts your cooldown a lot', 'utility', '#74b816', '🧰', _flag('tactical_reload')),
    Card('bouncy', 'BOUNCY', 'Bullets bounce more off walls and platforms', 'utility', '#20c997', '🪃', _add(max_bounces=2)),
    Card('barrage', 'BARRAGE', 'Each shot sprays several bullets', 'attack', '#f08c00', '🌧️', _flag('barrage')),
    Card('refresh', 'REFRESH', 'Hits refund part of your cooldown', 'utility', '#63e6be', '♻️', _flag('refresh')),
    Card('healing_field', 'HEALING FIELD', 'Blocking drops a healing zone', 'survival', '#51cf66', '➕', _flag('healing_field')),
    Card('shockwave', 'SHOCKWAVE', 'Blocking shoves nearby enemies away', 'utility', '#ff922b', '〰️', _flag('shockwave')),
    Card('shields_up', 'SHIELDS UP', 'Bigger block meter', 'survival', '#3b5bdb', '🪖', _shields_up),
    Card('teleport', 'TELEPORT', 'Blocking blinks you forward', 'special', '#be4bdb', '🌀', _flag('teleport')),
    Card('explosive_bullet', 'EXPLOSIVE BULLET', 'Bullets explode on impact', 'attack', '#ff6b6b', '🧨', _flag('explosive')),
    Card('decay', 'DECAY', 'Bullets weaken the longer they fly', 'attack', '#845ef7', '🕳️', _flag('decay')),
    Card('emp', 'EMP', 'Blocking stuns nearby enemies', 'special', '#00c2ff', '⚡', _flag('emp')),
    Card('lifestealer', 'LIFESTEALER', 'Heal for part of the damage you deal', 'survival', '#b197fc', '🧛', _add(lifesteal=0.3)),
    Card('parasite', 'PARASITE', 'The more damage you deal, the tougher you get', 'survival', '#74c0fc', '🪱', _flag('parasite')),
    Card('big_bullet', 'BIG BULLET', 'Bigger, heavier bullets', 'attack', '#ffa94d', '💣', _add(bullet_size=3, knockback_mult=0.5)),
    Card('combine', 'COMBINE', 'Much stronger attacks, but slower', 'attack', '#fab005', '⚙️', _combine),
    Card('glass_cannon', 'GLASS CANNON', 'High damage, low survivability', 'attack', '#f06595', '🥃', _glass_cannon),
    Card('saw', 'SAW', 'Blocking spawns a saw blade that attacks', 'special', '#ff922b', '🪚', _flag('saw')),
    Card('thruster', 'THRUSTER', 'More knockback and more speed', 'movement', '#845ef7', '🚀', _add(speed=1, knockback_mult=0.3)),
    Card('radar_shot', 'RADAR SHOT', 'Bullets curve toward enemies a little more', 'utility', '#12b886', '📡', _flag('radar_shot')),
    Card('fastball', 'FASTBALL', 'Much faster bullets', 'attack', '#fff9db', '⚾', _add(bullet_speed_mult=1.0)),
    Card('wind_up', 'WIND UP', 'The longer you charge, the harder the shot', 'attack', '#fab005', '🌀', _flag('wind_up')),
    Card('careful_planning', 'CAREFUL PLANNING', 'Shooting carefully is more accurate and stronger', 'utility', '#c0eb75', '🧠', _flag('careful_planning')),
    Card('tank', 'TANK', 'More health, but slower', 'survival', '#228be6', '🛡️', _add(max_hp=100, hp=100, speed=-2)),
    Card('defender', 'DEFENDER', 'Bigger block meter', 'survival', '#3b5bdb', '🧱', _defender),
    Card('burst', 'BURST', 'Shots come out in bursts', 'attack', '#74c0fc', '〰️', _add(burst=2)),
    Card('drill_ammo', 'DRILL AMMO', 'Bullets pierce through enemies', 'attack', '#adb5bd', '🪛', _flag('drill_ammo')),
    Card('implode', 'IMPLODE', 'Blocking pulls enemies toward you', 'utility', '#ae3ec9', '🕳️', _flag('implode')),
    Card('static_field', 'STATIC FIELD', 'Blocking drops a static zone', 'utility', '#339af0', '🌩️', _flag('static_field')),
    Card('leech', 'LEECH', 'Heal a little whenever you deal damage', 'survival', '#40c057', '🪱', _flag('leech')),
    Card('huge', 'HUGE', 'You and your bullets get bigger', 'special', '#1098ad', '🐘', _huge),
    Card('chase', 'CHASE', 'Bullets chase enemies more relentlessly', 'utility', '#ff6b6b', '🐾', _flag('chase')),
    Card('quick_shot', 'QUICK SHOT', 'Faster firing', 'attack', '#ffd43b', '⚡', _quick_shot),
    Card('steady_shot', 'STEADY SHOT', 'Bullets fly further and steadier', 'attack', '#ffe8cc', '🎯', _flag('steady_shot')),
    Card('ritual_countdown', 'RITUAL COUNTDOWN', 'Standing still charges your next shot', 'special', '#f06595', '⌛', _flag('ritual_countdown')),
    Card('chilling_presence', 'CHILLING PRESENCE', 'Nearby enemies slow down over time', 'utility', '#4dabf7', '🧊', _flag('chilling_presence')),
    Card('demonic_pact', 'DEMONIC PACT', 'Burn a little health for more damage', 'special', '#ff0000', '😈', _flag('demonic_pact')),
    Card('brawler', 'BRAWLER', 'Heavier bullets, strong up close', 'attack', '#e03131', '🥊', _add(damage_mult=0.5, max_hp=20, hp=20)),
    Card('overpower', 'OVERPOWER', 'Stronger the weaker your target is', 'attack', '#c92a2a', '👊', _flag('overpower')),
    Card('frost_slam', 'FROST SLAM', 'Blocking sends out an ice shockwave', 'utility', '#74c0fc', '❄️', _flag('frost_slam')),
    Card('cold_bullets', 'COLD BULLETS', 'Hits slow the target down', 'utility', '#99e9f2', '❄️', _flag('cold')),
    Card('dazzle', 'DAZZLE', 'Hits briefly stun', 'utility', '#ae3ec9', '✨', _flag('dazzle')),
    Card('ricochet', 'RICOCHET', 'Bullets bounce off walls harder', 'utility', '#ffd43b', '↩️', _ricochet),
    Card('remote', 'REMOTE', 'Steer your bullets a little', 'special', '#868e96', '🎮', _flag('remote')),
    Card('fast_forward', 'FAST FORWARD', 'Faster bullets, shorter lifetime', 'attack', '#fab005', '⏩', _fast_forward),
    Card('buckshot', 'BUCKSHOT', 'A spread of several pellets', 'special', '#f08c00', '🎇', _add(buckshot=3)),
]

CARD_BY_ID: dict[str, Card] = {card.id: card for card in CARDS}


# --- 공개 API --------------------------------------------------------------


def card_infos() -> list[dict[str, str]]:
    """PROTOCOL §3 CardInfo 목록 (apply 제외)."""
    return [
        {
            "id": c.id,
            "name": c.name,
            "desc": c.desc,
            "category": c.category,
            "color": c.color,
            "emoji": c.emoji,
        }
        for c in CARDS
    ]


def card_info(card_id: str) -> dict[str, str] | None:
    card = CARD_BY_ID.get(card_id)
    if card is None:
        return None
    return {
        "id": card.id,
        "name": card.name,
        "desc": card.desc,
        "category": card.category,
        "color": card.color,
        "emoji": card.emoji,
    }


def random_cards(n: int = C.CARD_CHOICES) -> list[Card]:
    """중복 없이 n 장을 뽑는다."""
    return random.sample(CARDS, min(n, len(CARDS)))


def apply_card(player: Player, card_id: str) -> bool:
    """카드를 적용하고 보유 목록에 추가한다. 없는 카드면 False."""
    card = CARD_BY_ID.get(card_id)
    if card is None:
        return False
    card.apply(player)
    player.cards.append(card.id)
    return True


def reset_card_state(player: Player) -> None:
    """리매치용 전체 초기화: 카드/플래그/스탯/상태이상/차징."""
    player.flags.clear()
    player.cards.clear()

    # 스탯
    player.max_hp = C.MAX_HP
    player.hp = C.MAX_HP
    player.speed = C.PLAYER_SPEED
    player.jump_power = C.JUMP_POWER
    player.width = C.PLAYER_SIZE
    player.height = C.PLAYER_SIZE
    player.damage_mult = 1.0
    player.knockback_mult = 1.0
    player.bullet_size = C.BASE_BULLET_SIZE
    player.bullet_speed_mult = 1.0
    player.max_bounces = 0
    player.cooldown = 0.0
    player.max_cooldown = C.BASE_COOLDOWN
    player.revives = 0
    player.lifesteal = 0.0
    player.buckshot = 0
    player.burst = 0
    player.max_jumps = 1
    player.jumps = 0

    # 가드 / 강공격
    player.block_meter_max = C.BLOCK_METER_MAX
    player.block_meter = C.BLOCK_METER_MAX
    player.blocking = False
    player.charging = False
    player.charge = 0.0
    player.windup = 0.0
    player.still_ticks = 0

    # 상태이상 타이머
    player.poison = 0
    player.cold_timer = 0
    player.dazzle_timer = 0
    player.silence_timer = 0
    player.echo_cooldown = 0
    player.blood_timer = 0
