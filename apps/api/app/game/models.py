"""게임 도메인 모델.

카드 효과가 붙이는 불리언 플래그는 개별 필드로 두지 않고 `flags: dict[str, float|bool]`
하나로 모은다(기존 JS 의 `player.xxxCard = true` 를 대체). 플래그 키는 카드 id 를 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.game import constants as C
from app.game import maps as M

Phase = Literal["waiting", "playing", "round_over", "picking", "finished"]
Mode = Literal["pvp", "training"]


@dataclass
class Vec:
    x: float = 0.0
    y: float = 0.0


@dataclass
class Inputs:
    left: bool = False
    right: bool = False
    jump: bool = False
    block: bool = False
    jump_consumed: bool = False


@dataclass
class Player:
    id: str
    nickname: str = "Guest"
    customization: dict[str, Any] = field(default_factory=lambda: dict(C.DEFAULT_CUSTOMIZATION))
    coins: int = 0

    # 물리
    x: float = 100.0
    y: float = 150.0
    vx: float = 0.0
    vy: float = 0.0
    width: float = C.PLAYER_SIZE
    height: float = C.PLAYER_SIZE
    grounded: bool = False
    jumps: int = 0
    max_jumps: int = 1

    # 스탯
    hp: float = C.MAX_HP
    max_hp: float = C.MAX_HP
    speed: float = C.PLAYER_SPEED
    jump_power: float = C.JUMP_POWER
    damage_mult: float = 1.0
    knockback_mult: float = 1.0
    bullet_size: float = C.BASE_BULLET_SIZE
    bullet_speed_mult: float = 1.0
    max_bounces: int = 0
    cooldown: float = 0.0
    max_cooldown: float = C.BASE_COOLDOWN
    revives: int = 0
    lifesteal: float = 0.0
    buckshot: int = 0
    burst: int = 0

    # 가드 / 강공격
    block_meter: float = C.BLOCK_METER_MAX
    block_meter_max: float = C.BLOCK_METER_MAX
    blocking: bool = False
    charging: bool = False
    charge: float = 0.0
    windup: float = 0.0
    still_ticks: int = 0

    # 상태이상 타이머(틱)
    poison: int = 0
    cold_timer: int = 0
    dazzle_timer: int = 0
    silence_timer: int = 0
    echo_cooldown: int = 0
    blood_timer: int = 0

    aim: Vec = field(default_factory=Vec)
    inputs: Inputs = field(default_factory=Inputs)
    cards: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    def has(self, flag: str) -> bool:
        return bool(self.flags.get(flag))


@dataclass
class Bot:
    id: str
    x: float = 100.0
    y: float = 150.0
    vx: float = 0.0
    vy: float = 0.0
    width: float = C.PLAYER_SIZE
    height: float = C.PLAYER_SIZE
    hp: float = C.MAX_HP
    max_hp: float = C.MAX_HP
    speed: float = 3.5
    jump_power: float = -14.0
    grounded: bool = False
    cooldown: float = 0.0
    customization: dict[str, Any] = field(default_factory=lambda: dict(C.DEFAULT_CUSTOMIZATION))
    # AI
    tier: str = "rookie"
    dir: int = 0
    ai_timer: int = 0
    jump_cooldown: int = 0
    #: 다시 조준하기까지 남은 지연(틱). 티어의 reaction 으로 채워진다.
    reaction_timer: float = 0.0
    #: 겨누는 지점. 사격뿐 아니라 클라이언트가 시선을 그리는 데도 쓴다.
    aim: Vec = field(default_factory=Vec)
    #: 회피 중 남은 틱(>0 이면 목표 거리와 반대로 움직인다)
    evade_timer: int = 0
    #: 티어 파라미터 사본(constants.BOT_TIERS[tier])
    traits: dict[str, float] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def trait(self, key: str, default: float = 0.0) -> float:
        return float(self.traits.get(key, default))

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class Bullet:
    id: int
    owner: str
    x: float
    y: float
    vx: float
    vy: float
    size: float = C.BASE_BULLET_SIZE
    color: str = "#ffd43b"
    damage: float = C.BASE_BULLET_DAMAGE
    knockback: float = C.BASE_KNOCKBACK
    life: int = C.BASE_BULLET_LIFE
    bounces: int = 0
    max_bounces: int = 0
    pierce: int = 0
    explode_radius: float = 85.0
    start_x: float = 0.0
    start_y: float = 0.0
    owner_aim: Vec = field(default_factory=Vec)
    active: bool = True
    flags: dict[str, Any] = field(default_factory=dict)

    def has(self, flag: str) -> bool:
        return bool(self.flags.get(flag))


@dataclass
class Zone:
    type: str
    x: float
    y: float
    radius: float
    duration: int
    owner: str


@dataclass
class ChatMessage:
    sender: str
    text: str
    time: int


@dataclass
class TrainingState:
    """훈련장 진행 상황과 성적. training 모드 방에만 붙는다(PROTOCOL §3 TrainingSnap)."""

    wave: int = 0
    #: 이번 웨이브에 스폰된 봇 총 수(남은 수는 room.bots 로 센다)
    wave_bots: int = 0
    state: str = "fighting"  # fighting | wave_clear | respawning
    timer: int = 0  # 다음 전환까지 남은 틱

    kills: int = 0
    deaths: int = 0
    best_wave: int = 0
    shots: int = 0  # 플레이어가 발사한 탄환 수
    hits: int = 0  # 그중 봇에 맞은 수
    damage_dealt: float = 0.0
    damage_taken: float = 0.0
    survived_ticks: int = 0  # 현재 목숨 기준


@dataclass
class Room:
    code: str
    mode: Mode = "pvp"
    max_players: int = 2
    phase: Phase = "waiting"
    players: dict[str, Player] = field(default_factory=dict)
    bots: dict[str, Bot] = field(default_factory=dict)
    bullets: list[Bullet] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)

    #: 방장이 대기실에서 고른 값. maps.RANDOM_ID("random") 일 수 있다.
    map_id: str = M.DEFAULT_ID
    #: 지금 실제로 깔려 있는 맵. random 선택은 게임 시작 때 여기로 확정된다.
    active_map_id: str = M.DEFAULT_ID
    platforms: list[dict[str, float]] = field(default_factory=lambda: M.platforms_of(M.DEFAULT_ID))

    scores: dict[str, int] = field(default_factory=dict)
    round_wins: dict[str, int] = field(default_factory=dict)
    loser_to_pick: str | None = None
    available_cards: list[str] = field(default_factory=list)
    winner_id: str | None = None
    #: 매치 종료(finished) 후 리매치에 동의한 플레이어 id. 전원 동의하면 바로 다시 시작한다.
    rematch_votes: set[str] = field(default_factory=set)

    tick: int = 0
    bullet_seq: int = 0
    bot_seq: int = 0
    round_end_timer: int = 0  # >0 이면 라운드 종료 연출 카운트다운
    #: 훈련장 진행 상태. pvp 방에서는 None 이다.
    training: TrainingState | None = None

    def next_bullet_id(self) -> int:
        self.bullet_seq += 1
        return self.bullet_seq

    def entities(self) -> list[Player | Bot]:
        return [*self.players.values(), *self.bots.values()]
