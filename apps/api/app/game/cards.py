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
    Card('empower', 'EMPOWER', '가드 후 다음 발이 강화됨', 'special', '#fcc419', '✨', _flag('empower')),
    Card('radiance', 'RADIANCE', '가드 시 빛의 파동이 퍼짐', 'special', '#ffd43b', '🌟', _flag('radiance')),
    Card('scavenger', 'SCAVENGER', '피해를 주면 재장전이 빨라짐', 'utility', '#845ef7', '🧲', _flag('scavenger')),
    Card('poison', 'POISON', '적중한 적에게 독을 누적시킴', 'attack', '#2f9e44', '☠️', _flag('poison', 1)),
    Card('mayhem', 'MAYHEM', '도탄이 많아지고 탄환이 더 난폭해짐', 'utility', '#d9480f', '💥', _mayhem),
    Card('bombs_away', 'BOMBS AWAY', '도탄한 탄환이 폭발함', 'attack', '#fa5252', '💣', _flag('bombs_away')),
    Card('pristine_persistence', 'PRISTINE PERSISTENCE', '체력이 가득할 때 더 강해짐', 'survival', '#4dabf7', '🫧', _flag('pristine')),
    Card('phoenix', 'PHOENIX', '한 번 죽어도 다시 살아남음', 'survival', '#f76707', '🐦‍🔥', _add(revives=1)),
    Card('quick_reload', 'QUICK RELOAD', '재사용 대기시간 감소', 'attack', '#74c0fc', '🔫', _quick_reload),
    Card('grow', 'GROW', '탄환이 날아갈수록 커지고 강해짐', 'attack', '#ffd43b', '🌱', _flag('grow')),
    Card('supernova', 'SUPERNOVA', '탄환이 터질 때 작은 폭발이 남음', 'attack', '#ff922b', '🌟', _flag('supernova')),
    Card('spray', 'SPRAY', '연사 속도는 빨라지고 한 발의 힘은 약해짐', 'attack', '#4dabf7', '🚿', _spray),
    Card('trickster', 'TRICKSTER', '발사가 조금 비틀려 예측이 어려워짐', 'utility', '#f06595', '🃏', _flag('trickster')),
    Card('target_bounce', 'TARGET BOUNCE', '튀는 탄환이 다음 적을 노림', 'utility', '#20c997', '🎯', _flag('target_bounce')),
    Card('timed_detonation', 'TIMED DETONATION', '시간이 지나면 탄환이 폭발함', 'attack', '#fd7e14', '⏱️', _flag('timed_detonation')),
    Card('sneaky', 'SNEAKY', '탄환이 작고 빠르게 지나감', 'utility', '#adb5bd', '🥷', _sneaky),
    Card('homing', 'HOMING', '탄환이 가장 가까운 적을 추적함', 'utility', '#bac8ff', '🧲', _flag('homing')),
    Card('silence', 'SILENCE', '적중한 적의 발사를 잠시 막음', 'utility', '#9775fa', '🔇', _flag('silence')),
    Card('taste_of_blood', 'TASTE OF BLOOD', '피해를 주면 이동 속도가 잠시 증가함', 'utility', '#c92a2a', '🩸', _flag('blood')),
    Card('toxic_cloud', 'TOXIC CLOUD', '맞은 자리 주변에 독 구름이 남음', 'attack', '#40c057', '☁️', _flag('toxic_cloud')),
    Card('echo', 'ECHO', '가드하면 반격 탄환이 하나 더 나감', 'utility', '#339af0', '📣', _flag('echo')),
    Card('shield_charge', 'SHIELD CHARGE', '가드 중 전진 돌진이 발생함', 'utility', '#228be6', '🛡️', _flag('shield_charge')),
    Card('tactical_reload', 'TACTICAL RELOAD', '가드 후 재사용 대기시간이 크게 줄어듦', 'utility', '#74b816', '🧰', _flag('tactical_reload')),
    Card('bouncy', 'BOUNCY', '탄환이 벽과 발판에 더 많이 튕김', 'utility', '#20c997', '🪃', _add(max_bounces=2)),
    Card('barrage', 'BARRAGE', '한 번 쏠 때 여러 발이 퍼져 나감', 'attack', '#f08c00', '🌧️', _flag('barrage')),
    Card('refresh', 'REFRESH', '적중 시 쿨타임이 일부 회복됨', 'utility', '#63e6be', '♻️', _flag('refresh')),
    Card('healing_field', 'HEALING FIELD', '가드하면 회복 장판이 생김', 'survival', '#51cf66', '➕', _flag('healing_field')),
    Card('shockwave', 'SHOCKWAVE', '가드가 주변 적을 밀쳐냄', 'utility', '#ff922b', '〰️', _flag('shockwave')),
    Card('shields_up', 'SHIELDS UP', '가드 게이지가 늘어남', 'survival', '#3b5bdb', '🪖', _shields_up),
    Card('teleport', 'TELEPORT', '가드하면 바라보는 방향으로 짧게 이동함', 'special', '#be4bdb', '🌀', _flag('teleport')),
    Card('explosive_bullet', 'EXPLOSIVE BULLET', '탄환이 맞는 순간 폭발함', 'attack', '#ff6b6b', '🧨', _flag('explosive')),
    Card('decay', 'DECAY', '탄환이 오래 갈수록 힘을 잃음', 'attack', '#845ef7', '🕳️', _flag('decay')),
    Card('emp', 'EMP', '가드 시 주변 적을 마비시킴', 'special', '#00c2ff', '⚡', _flag('emp')),
    Card('lifestealer', 'LIFESTEALER', '준 피해의 일부를 체력으로 돌려받음', 'survival', '#b197fc', '🧛', _add(lifesteal=0.3)),
    Card('parasite', 'PARASITE', '적에게 피해를 줄수록 더 버팀', 'survival', '#74c0fc', '🪱', _flag('parasite')),
    Card('big_bullet', 'BIG BULLET', '탄환이 커지고 더 무거워짐', 'attack', '#ffa94d', '💣', _add(bullet_size=3, knockback_mult=0.5)),
    Card('combine', 'COMBINE', '공격이 크게 강해지지만 느려짐', 'attack', '#fab005', '⚙️', _combine),
    Card('glass_cannon', 'GLASS CANNON', '공격력은 높지만 생존력은 낮아짐', 'attack', '#f06595', '🥃', _glass_cannon),
    Card('saw', 'SAW', '가드하면 톱날이 생겨 공격함', 'special', '#ff922b', '🪚', _flag('saw')),
    Card('thruster', 'THRUSTER', '반동과 이동 속도가 더 강해짐', 'movement', '#845ef7', '🚀', _add(speed=1, knockback_mult=0.3)),
    Card('radar_shot', 'RADAR SHOT', '탄환이 적을 향해 조금 더 잘 꺾임', 'utility', '#12b886', '📡', _flag('radar_shot')),
    Card('fastball', 'FASTBALL', '탄환 속도가 크게 증가함', 'attack', '#fff9db', '⚾', _add(bullet_speed_mult=1.0)),
    Card('wind_up', 'WIND UP', '천천히 준비할수록 더 강한 한 발', 'attack', '#fab005', '🌀', _flag('wind_up')),
    Card('careful_planning', 'CAREFUL PLANNING', '신중하게 쏘면 더 정확하고 강함', 'utility', '#c0eb75', '🧠', _flag('careful_planning')),
    Card('tank', 'TANK', '체력이 많아지지만 둔해짐', 'survival', '#228be6', '🛡️', _add(max_hp=100, hp=100, speed=-2)),
    Card('defender', 'DEFENDER', '가드 게이지가 늘어남', 'survival', '#3b5bdb', '🧱', _defender),
    Card('burst', 'BURST', '발사할 때 점사로 나감', 'attack', '#74c0fc', '〰️', _add(burst=2)),
    Card('drill_ammo', 'DRILL AMMO', '탄환이 적을 관통함', 'attack', '#adb5bd', '🪛', _flag('drill_ammo')),
    Card('implode', 'IMPLODE', '가드하면 적을 끌어당김', 'utility', '#ae3ec9', '🕳️', _flag('implode')),
    Card('static_field', 'STATIC FIELD', '가드하면 정전기 장판이 생김', 'utility', '#339af0', '🌩️', _flag('static_field')),
    Card('leech', 'LEECH', '피해를 줄 때 체력을 조금 회복함', 'survival', '#40c057', '🪱', _flag('leech')),
    Card('huge', 'HUGE', '플레이어와 탄환이 전부 커짐', 'special', '#1098ad', '🐘', _huge),
    Card('chase', 'CHASE', '탄환이 적을 더 집요하게 좇음', 'utility', '#ff6b6b', '🐾', _flag('chase')),
    Card('quick_shot', 'QUICK SHOT', '발사 속도가 더 빨라짐', 'attack', '#ffd43b', '⚡', _quick_shot),
    Card('steady_shot', 'STEADY SHOT', '탄환이 안정적으로 멀리 날아감', 'attack', '#ffe8cc', '🎯', _flag('steady_shot')),
    Card('ritual_countdown', 'RITUAL COUNTDOWN', '가만히 있을수록 다음 발사가 강해짐', 'special', '#f06595', '⌛', _flag('ritual_countdown')),
    Card('chilling_presence', 'CHILLING PRESENCE', '주변 적을 서서히 느리게 함', 'utility', '#4dabf7', '🧊', _flag('chilling_presence')),
    Card('demonic_pact', 'DEMONIC PACT', '발사 시 체력을 약간 태워 공격력을 올림', 'special', '#ff0000', '😈', _flag('demonic_pact')),
    Card('brawler', 'BRAWLER', '탄환이 더 묵직하고 가까운 싸움에 강함', 'attack', '#e03131', '🥊', _add(damage_mult=0.5, max_hp=20, hp=20)),
    Card('overpower', 'OVERPOWER', '상대가 약할수록 더 강해짐', 'attack', '#c92a2a', '👊', _flag('overpower')),
    Card('frost_slam', 'FROST SLAM', '가드 시 얼음 충격파가 퍼짐', 'utility', '#74c0fc', '❄️', _flag('frost_slam')),
    Card('cold_bullets', 'COLD BULLETS', '적중한 적의 이동을 둔화시킴', 'utility', '#99e9f2', '❄️', _flag('cold')),
    Card('dazzle', 'DAZZLE', '적중 시 짧게 기절시킴', 'utility', '#ae3ec9', '✨', _flag('dazzle')),
    Card('ricochet', 'RICOCHET', '탄환이 벽을 한 번 더 세게 튕김', 'utility', '#ffd43b', '↩️', _ricochet),
    Card('remote', 'REMOTE', '탄환을 조금 더 조종할 수 있음', 'special', '#868e96', '🎮', _flag('remote')),
    Card('fast_forward', 'FAST FORWARD', '탄환 속도는 더 빠르지만 수명은 짧아짐', 'attack', '#fab005', '⏩', _fast_forward),
    Card('buckshot', 'BUCKSHOT', '여러 발이 퍼져 나가는 산탄', 'special', '#f08c00', '🎇', _add(buckshot=3)),
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
