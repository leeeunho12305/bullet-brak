"""게임 월드 상수. 순수 상수만 둔다(로직 금지)."""

WIDTH = 1280.0
HEIGHT = 720.0
TICK_RATE = 60
TICK_SECONDS = 1.0 / TICK_RATE

GRAVITY = 0.6
FRICTION = 0.8
#: 이동 입력 1틱당 가속. 최고 속도까지 약 8틱 — 톡 치면 튀어나가지 않고 묵직하게 붙는다.
ACCEL = 0.65

MAX_HP = 120.0
PLAYER_SIZE = 30.0
#: 이동 입력으로 낼 수 있는 수평 속도 상한(px/틱).
#: 이 값이 점프 한 번의 수평 도달 거리도 정한다 — 체공 약 53틱 × 속도 = 약 265px.
#: 맵의 발판 간격은 그 도달 거리를 기준으로 잡혀 있다(maps.py 머리말).
#: 예전에는 이 상한이 사실상 걸리지 않았다(가속분이 넉백으로 오인돼 쌓여 18 까지 올라갔다).
#: sim.update_player / bots._physics 가 가속을 이 값에서 끊는다 — 값을 바꾸면 체감이 그대로 바뀐다.
PLAYER_SPEED = 5.0
JUMP_POWER = -16.0
BASE_COOLDOWN = 15.0
STRONG_COOLDOWN = 180.0
MAX_CHARGE = 60.0

BASE_BULLET_SPEED = 15.0
BASE_BULLET_DAMAGE = 20.0
BASE_BULLET_SIZE = 5.0
BASE_KNOCKBACK = 10.0
#: 월드가 1280px 로 넓어졌다 — 80틱(1200px)이면 맵을 가로지르기 전에 탄이 사라졌다.
BASE_BULLET_LIFE = 110

# 거리별 대미지 감쇠: 탄환이 날아간 거리에 비례해 위력이 줄어든다.
# 기본 탄(20) 기준 근접 30 -> 600px 이상 8 (레거시 DAMAGE_CLOSE/DAMAGE_FAR 수치).
DAMAGE_FALLOFF_RANGE = 600.0
DAMAGE_CLOSE_MULT = 1.5
DAMAGE_FAR_MULT = 0.4
DAMAGE_TABLE_DISTANCES = (0, 100, 200, 400, 600, 800)

# 산탄(BUCKSHOT) 전용 감쇠. 알이 여러 개라 근접에서 다 맞으면 어차피 아프다 —
# 그 대신 훨씬 짧은 거리에서 위력이 바닥나야 "붙어야 세다"가 성립한다.
# 4알 기준: 코앞 약 74, 260px 밖 약 7.
SCATTER_FALLOFF_RANGE = 260.0
SCATTER_FAR_MULT = 0.15
#: 산탄 카드가 알 하나당 깎는 위력. 4알이 다 맞아도 한 방에 죽지 않게 하는 값이다.
SCATTER_DAMAGE_MULT = 0.62

# --- 넉백 / 피격 반응 ---------------------------------------------------------
#: 피격 넉백 세기. 탄환이 날아온 방향으로 Bullet.knockback × 이 값만큼 민다.
KNOCKBACK_SCALE = 0.85
#: 그중 수직 성분에 곱하는 비율. 1.0 이면 위에서 맞을 때 그대로 내리꽂힌다.
KNOCKBACK_LIFT = 0.5
#: 방향과 무관하게 살짝 띄우는 양(맞았다는 게 보여야 한다).
HIT_POP = 2.0
#: 피격/폭발 한 번으로 얻을 수 있는 위쪽 속도의 상한(px/틱).
#: 산탄처럼 여러 발이 한꺼번에 맞아도 이보다 높이 솟지 않는다 — 점프(16)보다 한참 낮다.
#: 이 상한이 없으면 4~12발이 각자 띄우면서 맞은 쪽이 로켓처럼 날아오른다.
MAX_HIT_LIFT = 9.0
#: 이동 속도를 넘는(= 넉백으로 얻은) 수평 속도가 매 틱 남는 비율.
#: 1에 가까울수록 오래 밀린다. 0.94 면 약 0.5초 동안 밀려난다.
#: 이 완충이 없으면 넉백은 다음 틱의 속도 clamp 와 마찰에 그대로 지워진다.
KNOCKBACK_DECAY = 0.94
#: 초과 속도가 이보다 작아지면 넉백이 끝난 것으로 보고 평소 마찰에 넘긴다.
#: 기하급수 감쇠는 0 에 닿지 않는다 — 이 바닥이 없으면 맞은 사람이 영영 최고 속도로 미끄러진다.
KNOCKBACK_MIN = 0.25

# --- 탄환 조향 ---------------------------------------------------------------
#: REMOTE 카드가 "지금 조준하는 지점" 쪽으로 꺾는 세기.
REMOTE_STEER = 0.09
#: 조준점에 이만큼 가까워지면 더 꺾지 않는다. 없으면 커서 주위를 뱅뱅 돌기만 한다.
REMOTE_DEADZONE = 45.0

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
        "hp": 70.0, "speed": 2.1, "jump_power": -13.0,
        "fire_cooldown": 0.0, "damage": 0.0, "range": 0.0,
        "aim_error": 0.0, "lead": 0.0, "dodge": 0.0, "reaction": 0.0,
    },
    "rookie": {
        "hp": 100.0, "speed": 2.7, "jump_power": -14.0,
        "fire_cooldown": 100.0, "damage": 7.0, "range": 670.0,
        "aim_error": 0.20, "lead": 0.0, "dodge": 0.12, "reaction": 24.0,
    },
    "veteran": {
        "hp": 140.0, "speed": 3.5, "jump_power": -15.0,
        "fire_cooldown": 60.0, "damage": 10.0, "range": 1020.0,
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
BOT_BULLET_LIFE = 95
BOT_KNOCKBACK = 7.0

#: 맵을 못 고를 때의 최소 지형(클래식과 같은 배치). 실제 맵은 maps.py 가 쥐고 있다.
PLATFORMS = [
    {"x": 0.0, "y": 670.0, "width": 1280.0, "height": 50.0},
    {"x": 150.0, "y": 530.0, "width": 280.0, "height": 20.0},
    {"x": 850.0, "y": 530.0, "width": 280.0, "height": 20.0},
    {"x": 490.0, "y": 390.0, "width": 300.0, "height": 20.0},
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
