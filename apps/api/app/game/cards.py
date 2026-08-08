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
    """가드 게이지가 30% 천천히 닳는다(30초 -> 약 43초)."""
    p.flags["shields_up"] = True
    p.block_drain *= 0.7


def _defender(p: Player) -> None:
    """가드 게이지가 늘어난다(+75 = +15초)."""
    p.max_hp += 30
    p.hp += 30
    p.block_meter_max += 75.0
    p.block_meter += 75.0


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
#
# desc 규칙: "무슨 일이 일어나는가"를 **수치까지** 적는다. 분위기만 적어 두면 카드를
# 고를 때 판단이 서지 않는다. 시간은 초, 그 외에는 게임 안의 숫자를 그대로 쓴다.
# 여기 적힌 수치는 실제 구현(bullets/sim/stats)과 반드시 같아야 한다.

CARDS: list[Card] = [
    Card('empower', 'EMPOWER', '가드가 끝나면 다음 사격 한 번이 대미지 ×1.6', 'special', '#fcc419', '✨', _flag('empower')),
    Card('radiance', 'RADIANCE', '가드할 때와 적중할 때 빛 장판이 생겨 나만 조금씩 회복된다', 'special', '#ffd43b', '🌟', _flag('radiance')),
    Card('scavenger', 'SCAVENGER', '적을 맞히면 사격 쿨다운 -4틱. 가드 중에도 매 틱 -4', 'utility', '#845ef7', '🧲', _flag('scavenger')),
    Card('poison', 'POISON', '적중 시 독 10 중첩. 0.5초마다 1 피해를 주며 1씩 풀린다', 'attack', '#2f9e44', '☠️', _flag('poison', 1)),
    Card('mayhem', 'MAYHEM', '도탄 +5회, 대신 대미지 ×0.85', 'utility', '#d9480f', '💥', _mayhem),
    Card('bombs_away', 'BOMBS AWAY', '탄환이 발판에 튕길 때마다 반경 70 폭발 (대미지 35%)', 'attack', '#fa5252', '💣', _flag('bombs_away')),
    Card('pristine_persistence', 'PRISTINE PERSISTENCE', '체력이 가득한 상태로 쏘면 대미지 ×1.2', 'survival', '#4dabf7', '🫧', _flag('pristine')),
    Card('phoenix', 'PHOENIX', '쓰러져도 체력을 다 채우며 1회 부활 (낙사에는 발동하지 않음)', 'survival', '#f76707', '🐦‍🔥', _add(revives=1)),
    Card('quick_reload', 'QUICK RELOAD', '사격 쿨다운 -5틱 (15 → 10, 최소 2)', 'attack', '#74c0fc', '🔫', _quick_reload),
    Card('grow', 'GROW', '날아가는 동안 매 틱 대미지 +0.05, 크기 +0.01 로 자란다', 'attack', '#ffd43b', '🌱', _flag('grow')),
    Card('supernova', 'SUPERNOVA', '적중해도 수명이 다해도 반경 85 폭발이 남는다', 'attack', '#ff922b', '🌟', _flag('supernova')),
    Card('spray', 'SPRAY', '쿨다운이 3틱으로 고정된다. 대신 대미지 ×0.3', 'attack', '#4dabf7', '🚿', _spray),
    Card('trickster', 'TRICKSTER', '발사 각도가 매번 ±0.08rad 무작위로 틀어진다', 'utility', '#f06595', '🃏', _flag('trickster')),
    Card('target_bounce', 'TARGET BOUNCE', '도탄 +1회. 벽이나 발판에 한 번 튕긴 뒤부터 적을 추적한다', 'utility', '#20c997', '🎯', _flag('target_bounce')),
    Card('timed_detonation', 'TIMED DETONATION', '수명(80틱)이 다하면 반경 85 폭발 (대미지 60%)', 'attack', '#fd7e14', '⏱️', _flag('timed_detonation')),
    Card('sneaky', 'SNEAKY', '탄속 +15%, 탄 크기 -1 — 작고 빨라 눈에 잘 안 띈다', 'utility', '#adb5bd', '🥷', _sneaky),
    Card('homing', 'HOMING', '가장 가까운 적을 추적한다(조향 0.08). 지형을 통과한다', 'utility', '#bac8ff', '🧲', _flag('homing')),
    Card('silence', 'SILENCE', '적중한 적은 1초간 사격할 수 없다', 'utility', '#9775fa', '🔇', _flag('silence')),
    Card('taste_of_blood', 'TASTE OF BLOOD', '적을 맞히면 0.75초간 내 이동 속도 ×1.35', 'utility', '#c92a2a', '🩸', _flag('blood')),
    Card('toxic_cloud', 'TOXIC CLOUD', '적중 지점에 반경 85 독 구름이 4초간 남는다 (중심 초당 9 피해)', 'attack', '#40c057', '☁️', _flag('toxic_cloud')),
    Card('echo', 'ECHO', '가드로 탄을 튕겨낼 때마다 반격탄 1발 (대미지 65%, 0.5초 간격)', 'utility', '#339af0', '📣', _flag('echo')),
    Card('shield_charge', 'SHIELD CHARGE', '가드하는 동안 조준 방향으로 계속 밀려 나간다', 'utility', '#228be6', '🛡️', _flag('shield_charge')),
    Card('tactical_reload', 'TACTICAL RELOAD', '가드하는 동안 사격 쿨다운이 매 틱 8씩 줄어든다', 'utility', '#74b816', '🧰', _flag('tactical_reload')),
    Card('bouncy', 'BOUNCY', '도탄 +2회', 'utility', '#20c997', '🪃', _add(max_bounces=2)),
    Card('barrage', 'BARRAGE', '한 번 쏠 때 3발이 부채꼴로 퍼져 나간다', 'attack', '#f08c00', '🌧️', _flag('barrage')),
    Card('refresh', 'REFRESH', '적을 맞히면 사격 쿨다운 -8틱', 'utility', '#63e6be', '♻️', _flag('refresh')),
    Card('healing_field', 'HEALING FIELD', '가드하는 순간 반경 120 회복 장판이 1.5초간 생긴다 (최대 약 40 회복)', 'survival', '#51cf66', '➕', _flag('healing_field')),
    Card('shockwave', 'SHOCKWAVE', '가드하는 순간 반경 130 안의 적을 강하게 밀쳐낸다', 'utility', '#ff922b', '〰️', _flag('shockwave')),
    Card('shields_up', 'SHIELDS UP', '가드 게이지가 30% 천천히 닳는다 (30 → 43초)', 'survival', '#3b5bdb', '🪖', _shields_up),
    Card('teleport', 'TELEPORT', '가드하는 순간 조준 방향으로 110px 순간이동한다', 'special', '#be4bdb', '🌀', _flag('teleport')),
    Card('explosive_bullet', 'EXPLOSIVE BULLET', '적중하는 순간 반경 85 폭발 (대미지 55%). 내가 맞지는 않는다', 'attack', '#ff6b6b', '🧨', _flag('explosive')),
    Card('decay', 'DECAY', '매 틱 탄속 ×0.985, 대미지 ×0.99 로 점점 약해진다', 'attack', '#845ef7', '🕳️', _flag('decay')),
    Card('emp', 'EMP', '가드하는 순간 반경 130 안의 적을 0.4초 기절 + 침묵', 'special', '#00c2ff', '⚡', _flag('emp')),
    Card('lifestealer', 'LIFESTEALER', '적에게 준 피해의 30%를 체력으로 되돌려받는다', 'survival', '#b197fc', '🧛', _add(lifesteal=0.3)),
    Card('parasite', 'PARASITE', '적을 맞힐 때마다 최대 체력 +1 (매치 내내 쌓인다)', 'survival', '#74c0fc', '🪱', _flag('parasite')),
    Card('big_bullet', 'BIG BULLET', '탄 크기 +3, 넉백 ×1.5', 'attack', '#ffa94d', '💣', _add(bullet_size=3, knockback_mult=0.5)),
    Card('combine', 'COMBINE', '대미지 ×3, 대신 사격 쿨다운도 ×3', 'attack', '#fab005', '⚙️', _combine),
    Card('glass_cannon', 'GLASS CANNON', '대미지 배율 +1.0, 대신 최대 체력이 절반이 된다', 'attack', '#f06595', '🥃', _glass_cannon),
    Card('saw', 'SAW', '가드하는 순간 톱날 탄환 1발 (대미지 70%, 3회 도탄, 느림)', 'special', '#ff922b', '🪚', _flag('saw')),
    Card('thruster', 'THRUSTER', '이동 속도 +1, 넉백 ×1.3', 'movement', '#845ef7', '🚀', _add(speed=1, knockback_mult=0.3)),
    Card('radar_shot', 'RADAR SHOT', '탄환이 적 쪽으로 약하게 꺾인다(조향 0.05). 지형을 통과한다', 'utility', '#12b886', '📡', _flag('radar_shot')),
    Card('fastball', 'FASTBALL', '탄속 ×2 (배율 +1.0)', 'attack', '#fff9db', '⚾', _add(bullet_speed_mult=1.0)),
    Card('wind_up', 'WIND UP', '가만히 서서 모은 게이지만큼 대미지 최대 ×1.75', 'attack', '#fab005', '🌀', _flag('wind_up')),
    Card('careful_planning', 'CAREFUL PLANNING', '0.33초 이상 멈춰 있다가 쏘면 대미지 ×1.2', 'utility', '#c0eb75', '🧠', _flag('careful_planning')),
    Card('tank', 'TANK', '최대 체력 +100, 대신 이동 속도 -2', 'survival', '#228be6', '🛡️', _add(max_hp=100, hp=100, speed=-2)),
    Card('defender', 'DEFENDER', '최대 체력 +30, 가드 게이지 +75 (라운드당 +15초)', 'survival', '#3b5bdb', '🧱', _defender),
    Card('burst', 'BURST', '한 번 쏠 때 3발이 연달아 점사로 나간다', 'attack', '#74c0fc', '〰️', _add(burst=2)),
    Card('drill_ammo', 'DRILL AMMO', '탄환이 적 1명을 관통하고 계속 날아간다', 'attack', '#adb5bd', '🪛', _flag('drill_ammo')),
    Card('implode', 'IMPLODE', '가드하는 순간 반경 170 안의 적을 1초간 끌어당긴다', 'utility', '#ae3ec9', '🕳️', _flag('implode')),
    Card('static_field', 'STATIC FIELD', '가드하는 순간 반경 130 정전기 장판이 0.75초간 적을 기절·침묵시킨다', 'utility', '#339af0', '🌩️', _flag('static_field')),
    Card('leech', 'LEECH', '적을 맞힐 때마다 체력 +2', 'survival', '#40c057', '🪱', _flag('leech')),
    Card('huge', 'HUGE', '몸집 ×1.5, 탄 크기 +10 — 크게 때리고 크게 맞는다', 'special', '#1098ad', '🐘', _huge),
    Card('chase', 'CHASE', '탄환이 적을 강하게 추적한다(조향 0.14). 지형을 통과한다', 'utility', '#ff6b6b', '🐾', _flag('chase')),
    Card('quick_shot', 'QUICK SHOT', '사격 쿨다운 -7틱 (15 → 8, 최소 2)', 'attack', '#ffd43b', '⚡', _quick_shot),
    Card('steady_shot', 'STEADY SHOT', '탄환 수명 ×1.5, 거리에 따른 대미지 감쇠 절반', 'attack', '#ffe8cc', '🎯', _flag('steady_shot')),
    Card('ritual_countdown', 'RITUAL COUNTDOWN', '가만히 모은 게이지만큼 대미지 최대 ×1.5, 쏠 때마다 게이지 +8', 'special', '#f06595', '⌛', _flag('ritual_countdown')),
    Card('chilling_presence', 'CHILLING PRESENCE', '항상 반경 150 냉기를 뿜어 주변 적의 이동을 둔하게 만든다', 'utility', '#4dabf7', '🧊', _flag('chilling_presence')),
    Card('demonic_pact', 'DEMONIC PACT', '쏠 때마다 체력 2를 태우는 대신 대미지 ×1.35', 'special', '#ff0000', '😈', _flag('demonic_pact')),
    Card('brawler', 'BRAWLER', '대미지 배율 +0.5, 최대 체력 +20', 'attack', '#e03131', '🥊', _add(damage_mult=0.5, max_hp=20, hp=20)),
    Card('overpower', 'OVERPOWER', '상대 체력이 낮을수록 강해진다 — 빈사 상대에게 최대 ×1.5', 'attack', '#c92a2a', '👊', _flag('overpower')),
    Card('frost_slam', 'FROST SLAM', '가드하는 순간 반경 140 얼음 충격파가 적을 0.85초 둔화시킨다', 'utility', '#74c0fc', '❄️', _flag('frost_slam')),
    Card('cold_bullets', 'COLD BULLETS', '적중한 적은 1초간 이동 속도 ×0.65', 'utility', '#99e9f2', '❄️', _flag('cold')),
    Card('dazzle', 'DAZZLE', '적중한 적을 0.4초간 기절시킨다 (이동·점프·가드 불가)', 'utility', '#ae3ec9', '✨', _flag('dazzle')),
    Card('ricochet', 'RICOCHET', '도탄 +2회', 'utility', '#ffd43b', '↩️', _ricochet),
    Card('remote', 'REMOTE', '발사한 탄환이 지금 조준하는 지점 쪽으로 계속 휘어진다', 'special', '#868e96', '🎮', _flag('remote')),
    Card('fast_forward', 'FAST FORWARD', '탄속 크게 증가(배율 +0.4, 추가 ×1.25), 대신 수명 80 → 50틱', 'attack', '#fab005', '⏩', _fast_forward),
    Card('buckshot', 'BUCKSHOT', '한 번 쏠 때 4발이 산탄으로 퍼져 나간다', 'special', '#f08c00', '🎇', _add(buckshot=3)),
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
    player.block_drain = C.BLOCK_DRAIN
    player.empower_ready = False
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
