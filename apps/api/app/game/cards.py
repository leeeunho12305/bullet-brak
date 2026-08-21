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


def _buckshot(p: Player) -> None:
    """산탄. 알 4개가 전부 제값을 하면 코앞에서 한 방에 죽는다(4 × 30 = 120 = 최대 체력).

    알마다 위력을 깎고, 거리 감쇠도 따로 쓴다(stats.falloff_at 의 scatter 곡선).
    붙으면 세고 조금만 떨어지면 못 쓰는 무기가 되게 하는 게 요점이다.
    """
    p.buckshot += 3
    p.damage_mult *= C.SCATTER_DAMAGE_MULT


def _fast_forward(p: Player) -> None:
    p.flags["fast_forward"] = True
    p.bullet_speed_mult += 0.4


# --- 카드 목록 (JS CARDS 순서 유지) ----------------------------------------
#
# desc 규칙 — **처음 보는 사람이 읽고 바로 상상할 수 있어야 한다.**
#   · 시간은 초로 적는다. "틱"은 쓰지 않는다(플레이어에게 60틱=1초라는 정보가 없다).
#   · 배율 대신 증감 퍼센트로 적는다("×1.6" 이 아니라 "60% 늘어난다").
#   · 내부 용어(조향/수명/쿨다운/게이지 값)를 그대로 옮기지 않는다.
#   · 그래도 수치는 반드시 적는다. 분위기만 적어 두면 카드를 고를 때 판단이 서지 않는다.
#   · 여기 적힌 수치는 실제 구현(bullets/sim/stats)과 반드시 같아야 한다.

CARDS: list[Card] = [
    Card('empower', 'EMPOWER', '가드를 풀면 다음 한 발의 피해가 60% 늘어난다 (한 발만)', 'special', '#fcc419', '✨', _flag('empower')),
    Card('radiance', 'RADIANCE', '가드를 시작할 때와 적을 맞힐 때 빛 장판이 깔린다. 그 위에 선 나만 조금씩 회복한다 (가드 1회당 최대 약 11)', 'special', '#ffd43b', '🌟', _flag('radiance')),
    Card('scavenger', 'SCAVENGER', '적을 맞히면 다음 사격이 조금 빨라진다. 가드하는 동안에는 사격 준비가 5배 빠르게 끝난다', 'utility', '#845ef7', '🧲', _flag('scavenger')),
    Card('poison', 'POISON', '적중한 적이 5초에 걸쳐 10 피해를 더 입는다 (여러 장 겹치면 그만큼 길어진다)', 'attack', '#2f9e44', '☠️', _flag('poison', 1)),
    Card('mayhem', 'MAYHEM', '탄환이 5번 더 튕긴다. 대신 피해 15% 감소', 'utility', '#d9480f', '💥', _mayhem),
    Card('bombs_away', 'BOMBS AWAY', '탄환이 발판에 튕길 때마다 그 자리에서 작게 터진다 (내 피해의 35%, 반경 70)', 'attack', '#fa5252', '💣', _flag('bombs_away')),
    Card('pristine_persistence', 'PRISTINE PERSISTENCE', '체력이 가득한 상태로 쏘면 피해 20% 증가', 'survival', '#4dabf7', '🫧', _flag('pristine')),
    Card('phoenix', 'PHOENIX', '쓰러져도 체력을 모두 채우며 한 번 되살아난다 (떨어져 죽으면 발동하지 않는다)', 'survival', '#f76707', '🐦‍🔥', _add(revives=1)),
    Card('quick_reload', 'QUICK RELOAD', '연사가 빨라진다 — 사격 간격 0.25초 → 0.17초', 'attack', '#74c0fc', '🔫', _quick_reload),
    Card('grow', 'GROW', '탄환이 날아가는 동안 점점 커지고 세진다 (1초에 피해 +3, 크기 +0.6)', 'attack', '#ffd43b', '🌱', _flag('grow')),
    Card('supernova', 'SUPERNOVA', '탄환이 적을 맞혀도, 그냥 사라져도 그 자리에서 터진다 (반경 85)', 'attack', '#ff922b', '🌟', _flag('supernova')),
    Card('spray', 'SPRAY', '사격 간격이 0.05초로 고정된다 — 물총처럼 쏟아진다. 대신 피해 70% 감소', 'attack', '#4dabf7', '🚿', _spray),
    Card('trickster', 'TRICKSTER', '쏠 때마다 총구가 제멋대로 최대 4.6° 틀어진다', 'utility', '#f06595', '🃏', _flag('trickster')),
    Card('target_bounce', 'TARGET BOUNCE', '탄환이 1번 더 튕긴다. 벽이나 발판에 한 번 튕긴 뒤부터는 적을 따라간다', 'utility', '#20c997', '🎯', _flag('target_bounce')),
    Card('timed_detonation', 'TIMED DETONATION', '탄환이 1.3초 뒤 스스로 터진다 (내 피해의 60%, 반경 85)', 'attack', '#fd7e14', '⏱️', _flag('timed_detonation')),
    Card('sneaky', 'SNEAKY', '탄속이 기본의 15%만큼 빨라지고 탄이 작아진다 — 작고 빨라 눈에 잘 안 띈다', 'utility', '#adb5bd', '🥷', _sneaky),
    Card('homing', 'HOMING', '탄환이 가장 가까운 적을 따라간다 (보통 세기). 벽과 발판을 통과한다', 'utility', '#bac8ff', '🧲', _flag('homing')),
    Card('silence', 'SILENCE', '적중한 적은 1초 동안 총을 쏘지 못한다', 'utility', '#9775fa', '🔇', _flag('silence')),
    Card('taste_of_blood', 'TASTE OF BLOOD', '적을 맞히면 0.75초 동안 내 이동 속도 35% 증가', 'utility', '#c92a2a', '🩸', _flag('blood')),
    Card('toxic_cloud', 'TOXIC CLOUD', '적중한 자리에 독 구름이 4초간 남는다 (반경 85, 한가운데서 초당 9 피해)', 'attack', '#40c057', '☁️', _flag('toxic_cloud')),
    Card('echo', 'ECHO', '가드로 탄을 튕겨낼 때마다 쏜 상대 쪽으로 반격탄이 나간다 (내 피해의 65%, 0.5초에 한 번)', 'utility', '#339af0', '📣', _flag('echo')),
    Card('shield_charge', 'SHIELD CHARGE', '가드하는 동안 조준한 방향으로 계속 밀려 나간다 — 방패를 앞세우고 돌진', 'utility', '#228be6', '🛡️', _flag('shield_charge')),
    Card('tactical_reload', 'TACTICAL RELOAD', '가드하는 동안 사격 준비가 9배 빠르게 끝난다', 'utility', '#74b816', '🧰', _flag('tactical_reload')),
    Card('bouncy', 'BOUNCY', '탄환이 2번 더 튕긴다', 'utility', '#20c997', '🪃', _add(max_bounces=2)),
    Card('barrage', 'BARRAGE', '한 번 쏠 때 3발이 부채꼴로 퍼져 나간다', 'attack', '#f08c00', '🌧️', _flag('barrage')),
    Card('refresh', 'REFRESH', '적을 맞히면 다음 사격 준비가 0.13초 줄어든다', 'utility', '#63e6be', '♻️', _flag('refresh')),
    Card('healing_field', 'HEALING FIELD', '가드를 시작하면 회복 장판이 1.5초간 깔린다. 나만 회복하며 한가운데 서 있으면 최대 40 (반경 120)', 'survival', '#51cf66', '➕', _flag('healing_field')),
    Card('shockwave', 'SHOCKWAVE', '가드를 시작하면 주변의 적을 세게 밀쳐낸다 (반경 130)', 'utility', '#ff922b', '〰️', _flag('shockwave')),
    Card('shields_up', 'SHIELDS UP', '가드가 30% 오래 간다 — 라운드당 가드 시간 30초 → 43초', 'survival', '#3b5bdb', '🪖', _shields_up),
    Card('explosive_bullet', 'EXPLOSIVE BULLET', '적중하는 순간 터진다 (내 피해의 55%, 반경 85). 내 폭발에 내가 맞지는 않는다', 'attack', '#ff6b6b', '🧨', _flag('explosive')),
    Card('decay', 'DECAY', '탄환이 날아갈수록 느려지고 약해진다 (1초에 탄속 60%, 피해 45% 감소)', 'attack', '#845ef7', '🕳️', _flag('decay')),
    Card('emp', 'EMP', '가드를 시작하면 주변의 적이 0.4초 동안 움직이지도, 쏘지도 못한다 (반경 130)', 'special', '#00c2ff', '⚡', _flag('emp')),
    Card('lifestealer', 'LIFESTEALER', '적에게 준 피해의 30%만큼 내 체력이 찬다', 'survival', '#b197fc', '🧛', _add(lifesteal=0.3)),
    Card('parasite', 'PARASITE', '적을 맞힐 때마다 최대 체력 +1 (매치가 끝날 때까지 계속 쌓인다)', 'survival', '#74c0fc', '🪱', _flag('parasite')),
    Card('big_bullet', 'BIG BULLET', '탄이 커지고 넉백이 기본의 50%만큼 세진다 — 맞은 쪽이 크게 밀려난다', 'attack', '#ffa94d', '💣', _add(bullet_size=3, knockback_mult=0.5)),
    Card('combine', 'COMBINE', '피해가 3배가 된다. 대신 사격 간격도 3배로 늘어난다 (0.25초 → 0.75초)', 'attack', '#fab005', '⚙️', _combine),
    Card('glass_cannon', 'GLASS CANNON', '공격력에 기본 피해만큼을 더한다(혼자 들면 2배). 대신 최대 체력이 절반이 된다', 'attack', '#f06595', '🥃', _glass_cannon),
    Card('saw', 'SAW', '가드를 시작하면 톱날 탄환이 1발 굴러 나간다 (내 피해의 70%, 3번 튕기고 느리다)', 'special', '#ff922b', '🪚', _flag('saw')),
    Card('thruster', 'THRUSTER', '이동 속도가 빨라지고(+1) 내 넉백이 기본의 30%만큼 세진다', 'movement', '#845ef7', '🚀', _add(speed=1, knockback_mult=0.3)),
    Card('radar_shot', 'RADAR SHOT', '탄환이 적 쪽으로 살짝 꺾인다 (약한 유도). 벽과 발판을 통과한다', 'utility', '#12b886', '📡', _flag('radar_shot')),
    Card('fastball', 'FASTBALL', '탄속에 기본 탄속만큼을 더한다(혼자 들면 2배) — 거의 피할 틈이 없다', 'attack', '#fff9db', '⚾', _add(bullet_speed_mult=1.0)),
    Card('wind_up', 'WIND UP', '가만히 서 있으면 힘이 모인다. 1초쯤 모으고 쏘면 피해 75% 증가', 'attack', '#fab005', '🌀', _flag('wind_up')),
    Card('careful_planning', 'CAREFUL PLANNING', '0.33초 이상 멈춰 서 있다가 쏘면 피해 20% 증가', 'utility', '#c0eb75', '🧠', _flag('careful_planning')),
    Card('tank', 'TANK', '최대 체력 +100. 대신 이동 속도가 느려진다 (-2)', 'survival', '#228be6', '🛡️', _add(max_hp=100, hp=100, speed=-2)),
    Card('defender', 'DEFENDER', '최대 체력 +30, 라운드당 가드 시간 30초 → 45초', 'survival', '#3b5bdb', '🧱', _defender),
    Card('burst', 'BURST', '한 번 쏠 때 3발이 연달아 나간다 (점사)', 'attack', '#74c0fc', '〰️', _add(burst=2)),
    Card('drill_ammo', 'DRILL AMMO', '탄환이 적 한 명을 뚫고 계속 날아간다', 'attack', '#adb5bd', '🪛', _flag('drill_ammo')),
    Card('implode', 'IMPLODE', '가드를 시작하면 주변의 적을 1초 동안 내 쪽으로 끌어당긴다 (반경 170)', 'utility', '#ae3ec9', '🕳️', _flag('implode')),
    Card('static_field', 'STATIC FIELD', '가드를 시작하면 정전기 장판이 0.75초간 깔려, 그 안의 적이 움직이지도 쏘지도 못한다 (반경 130)', 'utility', '#339af0', '🌩️', _flag('static_field')),
    Card('leech', 'LEECH', '적을 맞힐 때마다 체력 +2', 'survival', '#40c057', '🪱', _flag('leech')),
    Card('huge', 'HUGE', '몸집이 1.5배가 되고 탄도 훨씬 커진다 — 크게 때리고 크게 맞는다', 'special', '#1098ad', '🐘', _huge),
    Card('chase', 'CHASE', '탄환이 적을 끈질기게 따라간다 (가장 센 유도). 벽과 발판을 통과한다', 'utility', '#ff6b6b', '🐾', _flag('chase')),
    Card('quick_shot', 'QUICK SHOT', '연사가 크게 빨라진다 — 사격 간격 0.25초 → 0.13초', 'attack', '#ffd43b', '⚡', _quick_shot),
    Card('steady_shot', 'STEADY SHOT', '탄환이 1.5배 오래 날아가고, 멀어질 때 줄어드는 피해가 절반이 된다', 'attack', '#ffe8cc', '🎯', _flag('steady_shot')),
    Card('ritual_countdown', 'RITUAL COUNTDOWN', '가만히 서서 모은 힘만큼 피해가 최대 50% 늘어난다. 쏠 때마다 힘이 조금 차오른다', 'special', '#f06595', '⌛', _flag('ritual_countdown')),
    Card('chilling_presence', 'CHILLING PRESENCE', '늘 냉기를 뿜어 주변(반경 150)의 적이 계속 느려진다', 'utility', '#4dabf7', '🧊', _flag('chilling_presence')),
    Card('demonic_pact', 'DEMONIC PACT', '쏠 때마다 내 체력을 2씩 태우는 대신 피해 35% 증가', 'special', '#ff0000', '😈', _flag('demonic_pact')),
    Card('brawler', 'BRAWLER', '공격력에 기본 피해의 50%를 더한다, 최대 체력 +20', 'attack', '#e03131', '🥊', _add(damage_mult=0.5, max_hp=20, hp=20)),
    Card('overpower', 'OVERPOWER', '상대의 체력이 적을수록 세진다 — 빈사 상대에게는 피해 50% 증가', 'attack', '#c92a2a', '👊', _flag('overpower')),
    Card('frost_slam', 'FROST SLAM', '가드를 시작하면 얼음 파동이 퍼져, 주변(반경 140)의 적이 0.8초 동안 35% 느려진다', 'utility', '#74c0fc', '❄️', _flag('frost_slam')),
    Card('cold_bullets', 'COLD BULLETS', '적중한 적이 1초 동안 35% 느려진다', 'utility', '#99e9f2', '❄️', _flag('cold')),
    Card('dazzle', 'DAZZLE', '적중한 적이 0.4초 동안 굳는다 (움직임·점프·가드 전부 불가)', 'utility', '#ae3ec9', '✨', _flag('dazzle')),
    Card('ricochet', 'RICOCHET', '탄환이 2번 더 튕긴다', 'utility', '#ffd43b', '↩️', _ricochet),
    Card('remote', 'REMOTE', '쏜 뒤에도 마우스로 몰아간다 — 탄환이 지금 조준하는 곳으로 계속 휘어진다', 'special', '#868e96', '🎮', _flag('remote')),
    Card('fast_forward', 'FAST FORWARD', '탄속이 약 1.75배가 된다. 대신 탄환이 1.3초 → 0.8초만 날아가고 사라진다', 'attack', '#fab005', '⏩', _fast_forward),
    Card('buckshot', 'BUCKSHOT', '한 번 쏠 때 4발이 산탄으로 퍼진다. 알마다 피해가 38% 낮고, 260px만 멀어져도 거의 안 아프다 — 붙어서 쏘는 무기', 'special', '#f08c00', '🎇', _buckshot),
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


def all_card_ids() -> list[str]:
    """카드 전체 목록. 훈련장에서 "아무거나 골라 보기"를 열어 줄 때 쓴다."""
    return [c.id for c in CARDS]


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
