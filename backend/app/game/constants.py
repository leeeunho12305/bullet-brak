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

BLOCK_METER_MAX = 600.0
BLOCK_DRAIN = 1.0
BLOCK_REGEN = 1.0

ROUNDS_TO_SCORE = 2  # 라운드 2승 = 1점
SCORE_TO_WIN = 5  # 5점 = 매치 승리
ROUND_END_DELAY_TICKS = 120  # 2초
CARD_CHOICES = 5
TRAINING_BOT_COUNT = 3

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

DEFAULT_CUSTOMIZATION = {"eye": 0, "mouth": 0, "detail": 0, "color": "#ff6b6b"}
