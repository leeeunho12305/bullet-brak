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
from collections.abc import Iterable
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
    Card('empower', 'EMPOWER', '가드하고 나서 쏘는 첫 발 위력 1.6배', 'special', '#fcc419', '✨', _flag('empower')),
    Card('radiance', 'RADIANCE', '가드·명중한 자리에 나만 회복하는 빛', 'special', '#ffd43b', '🌟', _flag('radiance')),
    Card('scavenger', 'SCAVENGER', '적을 맞히면 재장전이 4틱 빨라짐', 'utility', '#845ef7', '🧲', _flag('scavenger')),
    Card('poison', 'POISON', '맞힌 적이 0.5초마다 1씩 닳음 (10회)', 'attack', '#2f9e44', '☠️', _flag('poison', 1)),
    Card('mayhem', 'MAYHEM', '벽 튕김 +5회, 대신 위력 15% 감소', 'utility', '#d9480f', '💥', _mayhem),
    Card('bombs_away', 'BOMBS AWAY', '탄이 벽에 튕길 때마다 작게 폭발함', 'attack', '#fa5252', '💣', _flag('bombs_away')),
    Card('pristine_persistence', 'PRISTINE PERSISTENCE', '체력이 가득 찬 동안 위력 +20%', 'survival', '#4dabf7', '🫧', _flag('pristine')),
    Card('phoenix', 'PHOENIX', '죽어도 한 번은 체력을 채우고 부활함', 'survival', '#f76707', '🐦‍🔥', _add(revives=1)),
    Card('quick_reload', 'QUICK RELOAD', '재장전 15틱 → 10틱으로 빨라짐', 'attack', '#74c0fc', '🔫', _quick_reload),
    Card('grow', 'GROW', '탄이 날아가는 동안 계속 커지고 세짐', 'attack', '#ffd43b', '🌱', _flag('grow')),
    Card('supernova', 'SUPERNOVA', '명중할 때도, 수명이 다할 때도 폭발함', 'attack', '#ff922b', '🌟', _flag('supernova')),
    Card('spray', 'SPRAY', '재장전 3틱 초고속 연사, 위력은 30%', 'attack', '#4dabf7', '🚿', _spray),
    Card('trickster', 'TRICKSTER', '탄이 매번 조금씩 빗나가 예측이 어려움', 'utility', '#f06595', '🃏', _flag('trickster')),
    Card('target_bounce', 'TARGET BOUNCE', '튕김 +1, 한 번 튕긴 뒤엔 적을 따라감', 'utility', '#20c997', '🎯', _flag('target_bounce')),
    Card('timed_detonation', 'TIMED DETONATION', '빗나간 탄이 수명이 다하면 폭발함', 'attack', '#fd7e14', '⏱️', _flag('timed_detonation')),
    Card('sneaky', 'SNEAKY', '탄이 작아지고 15% 빨라짐', 'utility', '#adb5bd', '🥷', _sneaky),
    Card('homing', 'HOMING', '탄이 가장 가까운 적을 따라감', 'utility', '#bac8ff', '🧲', _flag('homing')),
    Card('silence', 'SILENCE', '맞은 적은 1초 동안 총을 못 쏨', 'utility', '#9775fa', '🔇', _flag('silence')),
    Card('taste_of_blood', 'TASTE OF BLOOD', '피해를 주면 0.75초 동안 35% 빨라짐', 'utility', '#c92a2a', '🩸', _flag('blood')),
    Card('toxic_cloud', 'TOXIC CLOUD', '명중한 자리에 독 구름이 0.6초 남음', 'attack', '#40c057', '☁️', _flag('toxic_cloud')),
    Card('echo', 'ECHO', '가드로 튕길 때 반격탄 1발이 나감', 'utility', '#339af0', '📣', _flag('echo')),
    Card('shield_charge', 'SHIELD CHARGE', '가드하는 동안 조준 방향으로 돌진함', 'utility', '#228be6', '🛡️', _flag('shield_charge')),
    Card('tactical_reload', 'TACTICAL RELOAD', '가드하는 동안 재장전이 쭉쭉 줄어듦', 'utility', '#74b816', '🧰', _flag('tactical_reload')),
    Card('bouncy', 'BOUNCY', '탄이 벽·발판에 2번 더 튕김', 'utility', '#20c997', '🪃', _add(max_bounces=2)),
    Card('barrage', 'BARRAGE', '한 번 쏠 때 3발이 부채꼴로 퍼짐', 'attack', '#f08c00', '🌧️', _flag('barrage')),
    Card('refresh', 'REFRESH', '적을 맞히면 재장전이 8틱 빨라짐', 'utility', '#63e6be', '♻️', _flag('refresh')),
    Card('healing_field', 'HEALING FIELD', '가드하면 나만 회복하는 장판이 깔림', 'survival', '#51cf66', '➕', _flag('healing_field')),
    Card('shockwave', 'SHOCKWAVE', '가드하면 주변 적을 계속 밀어냄', 'utility', '#ff922b', '〰️', _flag('shockwave')),
    Card('shields_up', 'SHIELDS UP', '가드 게이지 +150, 덜 닳고 더 빨리 참', 'survival', '#3b5bdb', '🪖', _shields_up),
    Card('teleport', 'TELEPORT', '가드하는 동안 조준한 곳으로 순간이동', 'special', '#be4bdb', '🌀', _flag('teleport')),
    Card('explosive_bullet', 'EXPLOSIVE BULLET', '명중하는 순간 주변까지 폭발 피해', 'attack', '#ff6b6b', '🧨', _flag('explosive')),
    Card('decay', 'DECAY', '탄이 날아갈수록 느려지고 약해짐', 'attack', '#845ef7', '🕳️', _flag('decay')),
    Card('emp', 'EMP', '가드하면 넓게 퍼지는 전자 펄스로 적이 굳음', 'special', '#00c2ff', '⚡', _flag('emp')),
    Card('lifestealer', 'LIFESTEALER', '준 피해의 30%만큼 체력을 회복함', 'survival', '#b197fc', '🧛', _add(lifesteal=0.3)),
    Card('parasite', 'PARASITE', '적을 맞힐 때마다 최대 체력 +1', 'survival', '#74c0fc', '🪱', _flag('parasite')),
    Card('big_bullet', 'BIG BULLET', '탄 크기 +3, 넉백 50% 증가', 'attack', '#ffa94d', '💣', _add(bullet_size=3, knockback_mult=0.5)),
    Card('combine', 'COMBINE', '위력 3배, 대신 재장전도 3배 느려짐', 'attack', '#fab005', '⚙️', _combine),
    Card('glass_cannon', 'GLASS CANNON', '위력 2배, 대신 최대 체력이 절반', 'attack', '#f06595', '🥃', _glass_cannon),
    Card('saw', 'SAW', '가드하는 동안 톱날 탄이 계속 나감', 'special', '#ff922b', '🪚', _flag('saw')),
    Card('thruster', 'THRUSTER', '이동 속도 +1, 넉백 30% 증가', 'movement', '#845ef7', '🚀', _add(speed=1, knockback_mult=0.3)),
    Card('radar_shot', 'RADAR SHOT', '탄이 적 쪽으로 살짝 휘어감', 'utility', '#12b886', '📡', _flag('radar_shot')),
    Card('fastball', 'FASTBALL', '탄속이 2배가 됨', 'attack', '#fff9db', '⚾', _add(bullet_speed_mult=1.0)),
    Card('wind_up', 'WIND UP', '가만히 있다 쏘면 위력 최대 +75%', 'attack', '#fab005', '🌀', _flag('wind_up')),
    Card('careful_planning', 'CAREFUL PLANNING', '0.3초 멈췄다 쏘면 위력 +20%', 'utility', '#c0eb75', '🧠', _flag('careful_planning')),
    Card('tank', 'TANK', '최대 체력 +100, 대신 이동 속도 -2', 'survival', '#228be6', '🛡️', _add(max_hp=100, hp=100, speed=-2)),
    Card('defender', 'DEFENDER', '최대 체력 +30, 가드 게이지 +120', 'survival', '#3b5bdb', '🧱', _defender),
    Card('burst', 'BURST', '한 번 쏘면 같은 방향으로 3연발', 'attack', '#74c0fc', '〰️', _add(burst=2)),
    Card('drill_ammo', 'DRILL AMMO', '탄이 적 한 명을 뚫고 지나감', 'attack', '#adb5bd', '🪛', _flag('drill_ammo')),
    Card('implode', 'IMPLODE', '가드하면 주변 적을 끌어당김', 'utility', '#ae3ec9', '🕳️', _flag('implode')),
    Card('static_field', 'STATIC FIELD', '가드하면 오래 남는 정전기 장판이 깔림', 'utility', '#339af0', '🌩️', _flag('static_field')),
    Card('leech', 'LEECH', '적을 맞힐 때마다 체력 +2', 'survival', '#40c057', '🪱', _flag('leech')),
    Card('huge', 'HUGE', '몸과 탄이 1.5배로 커짐 (맞기도 쉬움)', 'special', '#1098ad', '🐘', _huge),
    Card('chase', 'CHASE', '탄이 가장 가까운 적을 끈질기게 따라감', 'utility', '#ff6b6b', '🐾', _flag('chase')),
    Card('quick_shot', 'QUICK SHOT', '재장전 15틱 → 8틱으로 빨라짐', 'attack', '#ffd43b', '⚡', _quick_shot),
    Card('steady_shot', 'STEADY SHOT', '거리에 따른 위력 변동이 줄고 더 멀리', 'attack', '#ffe8cc', '🎯', _flag('steady_shot')),
    Card('ritual_countdown', 'RITUAL COUNTDOWN', '쏠 때마다 기운이 쌓임 (WIND UP과 함께)', 'special', '#f06595', '⌛', _flag('ritual_countdown')),
    Card('chilling_presence', 'CHILLING PRESENCE', '가까이 온 적을 계속 느리게 만듦', 'utility', '#4dabf7', '🧊', _flag('chilling_presence')),
    Card('demonic_pact', 'DEMONIC PACT', '체력 2를 태워 쏨 — 아플수록 강해짐', 'special', '#ff0000', '😈', _flag('demonic_pact')),
    Card('brawler', 'BRAWLER', '위력 +50%, 최대 체력 +20', 'attack', '#e03131', '🥊', _add(damage_mult=0.5, max_hp=20, hp=20)),
    Card('overpower', 'OVERPOWER', '상대 체력이 낮을수록 위력 최대 +60%', 'attack', '#c92a2a', '👊', _flag('overpower')),
    Card('frost_slam', 'FROST SLAM', '가드하면 주변 적이 0.8초 느려짐', 'utility', '#74c0fc', '❄️', _flag('frost_slam')),
    Card('cold_bullets', 'COLD BULLETS', '맞은 적이 1초 동안 35% 느려짐', 'utility', '#99e9f2', '❄️', _flag('cold')),
    Card('dazzle', 'DAZZLE', '맞은 적이 0.3초 굳어 못 움직임', 'utility', '#ae3ec9', '✨', _flag('dazzle')),
    Card('ricochet', 'RICOCHET', '탄이 벽·발판에 1번 더 튕김', 'utility', '#ffd43b', '↩️', _ricochet),
    Card('remote', 'REMOTE', '쏜 탄이 내 마우스 커서를 따라감', 'special', '#868e96', '🎮', _flag('remote')),
    Card('fast_forward', 'FAST FORWARD', '탄속 크게 증가, 대신 사거리가 짧아짐', 'attack', '#fab005', '⏩', _fast_forward),
    Card('buckshot', 'BUCKSHOT', '한 번 쏠 때 4발이 산탄으로 퍼짐', 'special', '#f08c00', '🎇', _add(buckshot=3)),
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


def random_cards(n: int = C.CARD_CHOICES, owned: Iterable[str] = ()) -> list[Card]:
    """중복 없이 n 장을 뽑는다. 이미 가진 카드(owned)는 후보에서 뺀다.

    남은 후보가 n 장보다 적으면(= 거의 다 모았으면) 가진 카드로 채워서라도
    n 장을 만든다. 선택창이 비어 라운드가 멈추는 쪽이 훨씬 나쁘다.
    """
    taken = set(owned)
    pool = [c for c in CARDS if c.id not in taken]
    picked = random.sample(pool, min(n, len(pool)))
    if len(picked) < n:
        rest = [c for c in CARDS if c.id in taken]
        picked += random.sample(rest, min(n - len(picked), len(rest)))
    return picked


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
    player.burst_queue = 0
    player.burst_timer = 0
    player.max_jumps = 1
    player.jumps = 0

    # 가드 / 강공격
    player.block_meter_max = C.BLOCK_METER_MAX
    player.block_meter = C.BLOCK_METER_MAX
    player.blocking = False
    player.guard_broken = False
    player.charging = False
    player.charge = 0.0
    player.windup = 0.0
    player.empower_ready = False
    player.still_ticks = 0

    # 상태이상 타이머
    player.poison = 0
    player.cold_timer = 0
    player.dazzle_timer = 0
    player.silence_timer = 0
    player.echo_cooldown = 0
    player.blood_timer = 0
