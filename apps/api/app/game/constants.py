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

# 거리별 대미지 감쇠: 탄환이 날아간 거리에 비례해 위력이 줄어든다.
# 기본 탄(20) 기준 근접 30 -> 600px 이상 8 (레거시 DAMAGE_CLOSE/DAMAGE_FAR 수치).
DAMAGE_FALLOFF_RANGE = 600.0
DAMAGE_CLOSE_MULT = 1.5
DAMAGE_FAR_MULT = 0.4
DAMAGE_TABLE_DISTANCES = (0, 100, 200, 400, 600, 800)

# --- 가드 -------------------------------------------------------------------
# 가드는 게이지다. 누르고 있는 동안만 줄고, 손을 떼면 그 자리에서 멈춘다(언제든 끊을 수 있다).
# 라운드가 시작될 때만 가득 차고 라운드 안에서는 회복되지 않는다 — 아껴 써야 하는 자원이다.
BLOCK_METER_MAX = 150.0
#: 가득 찬 게이지를 계속 눌러 다 쓰는 데 걸리는 시간(초)
BLOCK_DRAIN_SECONDS = 30.0
#: 가드 1틱당 소모량. 150 / (30초 × 60틱) = 0.0833
BLOCK_DRAIN = BLOCK_METER_MAX / (BLOCK_DRAIN_SECONDS * TICK_RATE)

# --- 폭발 / 장판 -------------------------------------------------------------
#: 폭발 연출용 blast 장판이 남아 있는 틱. 클라 renderer 의 BLAST_TICKS 와 같아야 한다.
BLAST_TICKS = 12
#: IMPLODE 장판이 1틱에 끌어당기는 거리(px). 속도만 건드리면 마찰·이동 입력에 지워진다.
IMPLODE_PULL = 3.0

#: 독 구름(TOXIC CLOUD). 예전보다 훨씬 약하지만 훨씬 오래 깔려 있다.
TOXIC_TICKS = 240  # 4초
TOXIC_RADIUS = 85.0
TOXIC_TICK_DAMAGE = 0.15  # 중심에서 1틱당 피해(= 초당 9)
TOXIC_STACK_PERIOD = 30  # 이 주기마다 독 1 중첩

ROUNDS_TO_SCORE = 2  # 라운드 2승 = 1점
SCORE_TO_WIN = 5  # 5점 = 매치 승리
ROUND_END_DELAY_TICKS = 120  # 2초
CARD_CHOICES = 5

# 코인 보상(PvP 전용). 튜토리얼 문구가 web/types/game.ts 의 같은 값을 쓴다.
COINS_ROUND_WIN = 10
COINS_MATCH_WIN = 100

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
