"""게임 월드 상수. 순수 상수만 둔다(로직 금지)."""

WIDTH = 800.0
HEIGHT = 600.0
TICK_RATE = 60
TICK_SECONDS = 1.0 / TICK_RATE

GRAVITY = 0.6
FRICTION = 0.8
ACCEL = 0.8

MAX_HP = 120.0
PLAYER_SIZE = 30.0
PLAYER_SPEED = 5.0
JUMP_POWER = -16.0
BASE_COOLDOWN = 15.0
STRONG_COOLDOWN = 180.0
MAX_CHARGE = 60.0

BASE_BULLET_SPEED = 15.0
BASE_BULLET_DAMAGE = 20.0
BASE_BULLET_SIZE = 5.0
BASE_KNOCKBACK = 10.0
BASE_BULLET_LIFE = 80
# 한 번 튕길 때마다 늘어나는 탄 수명(틱). 도탄 카드를 먹었는데 벽에 맞고 바로
# 꺼지면 튕길 기회 자체가 없다. 맵을 한 번 가로지르는 데 드는 틱(800px / 15px ≈ 54)
# 보다 조금 크게 잡아, "몇 번 튕기느냐"는 시간이 아니라 max_bounces 가 정하게 한다.
BOUNCE_LIFE_BONUS = 55
# --- 카드 효과 수치 ---------------------------------------------------------
EMPOWER_MULT = 1.6  # EMPOWER: 가드 후 첫 발 위력 배율
OVERPOWER_MAX_BONUS = 0.6  # OVERPOWER: 상대가 빈사일 때 위력 +60%
DEMONIC_MAX_BONUS = 0.8  # DEMONIC PACT: 내 체력이 바닥일 때 위력 +80%
STEADY_FALLOFF_RELIEF = 0.5  # STEADY SHOT: 거리에 따른 위력 변동을 절반으로
STEADY_LIFE_BONUS = 40  # STEADY SHOT: 탄 수명(틱)
DAZZLE_HIT_TICKS = 18  # DAZZLE: 적중 시 기절 시간
BLOOD_SPEED_MULT = 1.35  # TASTE OF BLOOD: 피해를 준 뒤 이동 속도 배율

# 탄환 조향 세기(틱당 방향 보정 비율). 클수록 급하게 꺾인다.
REMOTE_STEER = 0.08  # REMOTE: 주인의 마우스 커서를 실시간으로 좇는다
RADAR_STEER = 0.04  # RADAR SHOT: 살짝 휘는 정도
HOMING_STEER = 0.08  # HOMING: 확실히 따라간다
CHASE_STEER = 0.13  # CHASE: 집요하게 따라붙는다

# BURST 점사 간격(틱). 한 번 누르면 같은 방향으로 이 간격마다 한 발씩 더 나간다.
BURST_INTERVAL = 4

# 거리별 대미지 감쇠: 탄환이 날아간 거리에 비례해 위력이 줄어든다.
# 기본 탄(20) 기준 근접 30 -> 600px 이상 8 (레거시 DAMAGE_CLOSE/DAMAGE_FAR 수치).
DAMAGE_FALLOFF_RANGE = 600.0
DAMAGE_CLOSE_MULT = 1.5
DAMAGE_FAR_MULT = 0.4
DAMAGE_TABLE_DISTANCES = (0, 100, 200, 400, 600, 800)

BLOCK_METER_MAX = 600.0
# 가드 게이지는 시간이 지난다고 닳지 않는다. 누르고 있는 동안 가드는 계속 유지되고,
# 탄을 실제로 막아 낼 때만(bullets._reflect) 그 탄의 위력에 비례해 닳는다.
# 기본 탄(위력 20) 기준 한 발에 60 → 꽉 찬 게이지로 10발을 받아친다.
BLOCK_COST_PER_DAMAGE = 3.0
BLOCK_REGEN = 2.0  # 가드를 놓으면 초당 120 회복(꽉 차는 데 5초)
# 게이지를 다 쓰면 가드가 깨진다. 여기까지 다시 차야 가드를 올릴 수 있다.
BLOCK_RECOVER_RATIO = 1.0

ROUNDS_TO_SCORE = 2  # 라운드 2승 = 1점
SCORE_TO_WIN = 5  # 5점 = 매치 승리
ROUND_END_DELAY_TICKS = 120  # 2초
CARD_CHOICES = 5

# --- 훈련장 -----------------------------------------------------------------
# 봇 티어. 허수아비 → 견습 → 정예 순으로 조준/사격/회피가 붙는다.
#   fire_cooldown: 0 이면 사격하지 않는다(허수아비)
#   aim_error    : 조준 각도에 섞는 최대 오차(라디안)
#   lead         : 플레이어 속도를 읽고 미리 쏘는가(선도 사격)
#   dodge        : 날아오는 탄환을 감지했을 때 회피를 시도할 확률
#   reaction     : 플레이어를 다시 조준하기까지의 지연(틱) — 클수록 굼뜨다
BOT_TIERS: dict[str, dict[str, float]] = {
    "dummy": {
        "hp": 70.0, "speed": 2.6, "jump_power": -13.0,
        "fire_cooldown": 0.0, "damage": 0.0, "range": 0.0,
        "aim_error": 0.0, "lead": 0.0, "dodge": 0.0, "reaction": 0.0,
    },
    "rookie": {
        "hp": 100.0, "speed": 3.4, "jump_power": -14.0,
        "fire_cooldown": 100.0, "damage": 7.0, "range": 420.0,
        "aim_error": 0.20, "lead": 0.0, "dodge": 0.12, "reaction": 24.0,
    },
    "veteran": {
        "hp": 140.0, "speed": 4.4, "jump_power": -15.0,
        "fire_cooldown": 60.0, "damage": 10.0, "range": 640.0,
        "aim_error": 0.06, "lead": 1.0, "dodge": 0.45, "reaction": 10.0,
    },
}
BOT_TIER_ORDER = ("dummy", "rookie", "veteran")

#: 웨이브별 봇 구성. 표를 넘어서면 마지막 구성을 쓰고 체력만 올린다.
TRAINING_WAVES: tuple[tuple[str, ...], ...] = (
    ("dummy", "dummy", "dummy"),
    ("rookie", "dummy", "dummy"),
    ("rookie", "rookie", "dummy"),
    ("rookie", "rookie", "rookie"),
    ("veteran", "rookie", "rookie"),
    ("veteran", "veteran", "rookie"),
)
TRAINING_HP_SCALE_PER_WAVE = 0.08  # 표를 넘어선 웨이브마다 체력 +8%
TRAINING_MAX_HP_SCALE = 2.5
TRAINING_WAVE_BREAK_TICKS = 90  # 웨이브 전멸 후 카드 선택까지 1.5초
TRAINING_RESPAWN_TICKS = 180  # 사망 후 부활까지 3초
BOT_SIGHT_SAMPLES = 12  # 시야 판정을 위해 사선을 몇 등분해 검사하는가

# 봇 탄환(플레이어 탄환보다 느리고 약하다 — 피할 수 있어야 훈련이 된다)
BOT_BULLET_SPEED = 11.0
BOT_BULLET_SIZE = 4.5
BOT_BULLET_LIFE = 70
BOT_KNOCKBACK = 7.0

PLATFORMS = [
    {"x": 0.0, "y": 550.0, "width": 800.0, "height": 50.0},
    {"x": 100.0, "y": 400.0, "width": 200.0, "height": 20.0},
    {"x": 500.0, "y": 400.0, "width": 200.0, "height": 20.0},
    {"x": 300.0, "y": 250.0, "width": 200.0, "height": 20.0},
]

AVATAR_PALETTE = [
    "#4dabf7",
    "#51cf66",
    "#845ef7",
    "#ffa94d",
    "#ff6b6b",
    "#ffd43b",
    "#20c997",
    "#3bc9db",
    "#5c7cfa",
    "#f06595",
    "#94d82d",
]

# 편집기 파츠 슬롯. 클라 types/game.ts 의 PartSlot 과 같은 값이어야 한다.
PART_SLOTS = ("eye", "mouth", "detail", "detail2")
# 파츠 위치 보정 한계(몸통 박스 대비 비율). 클라 game/avatars.ts 의 MAX_OFFSET 과 같은 값.
MAX_PART_OFFSET = 0.32
# 파츠 인덱스 상한. 클라 카탈로그보다 넉넉하게 두고, 실제 그림은 클라가 clamp 한다.
MAX_PART_INDEX = 199

DEFAULT_CUSTOMIZATION = {
    "eye": 0,
    "mouth": 0,
    "detail": 0,
    "detail2": 0,
    "color": "#ff6b6b",
    "offsets": {},
}
