# Bullet Brak — 네트워크 / 내부 인터페이스 계약서

이 문서는 **백엔드(FastAPI)와 프론트엔드(React)가 동시에 개발되어도 어긋나지 않도록** 하는 단일 기준이다.
여기 적힌 키 이름/타입은 임의로 바꾸지 않는다. 바꿔야 하면 이 문서를 먼저 고친다.

- 월드 좌표계: 고정 **800 x 600** (`WIDTH x HEIGHT`). 캔버스는 CSS로만 스케일한다.
- 틱레이트: **60Hz** (서버 권위 시뮬레이션). 매 틱 전체 스냅샷 브로드캐스트.
- 직렬화: JSON. 모든 메시지는 `{"type": "...", ...payload}` 형태의 **평평한(flat) 객체**.
- 키 네이밍: 서버/전송 = `snake_case`, 프론트 TS 타입도 **동일하게 snake_case 유지**(변환 레이어 없음).

---

## 1. REST API (`/api`)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | - | `{"status":"ok"}` |
| POST | `/api/rooms` | `{"mode":"pvp"\|"training","max_players":2}` | `{"code":"123456","mode":"pvp","max_players":2}` |
| GET | `/api/rooms/{code}` | - | `{"code","mode","max_players","player_count","phase"}` / 404 `{"detail":"..."}` |
| GET | `/api/cards` | - | `[{"id","name","desc","category","color","emoji"}]` |

`mode`: `pvp`(방 대전) / `training`(봇 3마리 솔로 연습).

---

## 2. WebSocket

접속: `ws://<host>/ws/{code}?nickname=<닉>`

접속 직후 클라이언트가 **반드시** `join` 을 1회 보낸다. 서버는 `welcome` 으로 응답한다.
방이 없거나 가득 찼으면 서버는 `error` 를 보내고 close(코드 4404 / 4409).

### 2.1 Client → Server

| type | payload | 설명 |
|---|---|---|
| `join` | `{"nickname":str,"customization":Customization,"coins":int}` | 입장(최초 1회) |
| `input` | `{"left":bool,"right":bool,"jump":bool,"block":bool}` | 이동/가드 입력 (변경 시에만 전송) |
| `aim` | `{"x":float,"y":float}` | 마우스 월드 좌표 (최대 30Hz 스로틀) |
| `shoot` | `{}` | 일반 사격 |
| `strong_start` | `{}` | 강공격 차징 시작 |
| `strong_release` | `{}` | 강공격 발사 |
| `pick_card` | `{"card_id":str}` | 카드 선택 (패자만 유효) |
| `chat` | `{"text":str}` | 채팅 (서버에서 욕설 마스킹) |
| `start_game` | `{}` | 방장이 게임 시작 |
| `restart` | `{}` | 종료 후 리매치 |
| `avatar` | `{"customization":Customization}` | 대기 중 외형 변경 |

### 2.2 Server → Client

| type | payload |
|---|---|
| `welcome` | `{"player_id":str,"room":RoomState}` |
| `room_state` | `{"room":RoomState}` |
| `state` | `Snapshot` (60Hz) |
| `chat` | `{"message":ChatMessage}` |
| `event` | `{"event":"round_over"\|"match_over"\|"card_phase"\|"game_started","winner_id":str\|null,"loser_id":str\|null}` |
| `error` | `{"message":str}` |

---

## 3. 데이터 구조 (JSON)

```jsonc
Customization = { "eye": 0, "mouth": 0, "detail": 0, "color": "#ff6b6b" }

RoomState = {
  "code": "123456", "mode": "pvp", "max_players": 2, "phase": "waiting",
  "players": [ { "id": "...", "nickname": "익명", "customization": Customization, "coins": 0 } ]
}
// phase: "waiting" | "playing" | "round_over" | "picking" | "finished"

PlayerSnap = {
  "id": str, "nickname": str, "customization": Customization,
  "x": f, "y": f, "width": f, "height": f, "vx": f, "vy": f,
  "hp": f, "max_hp": f, "alive": bool,
  "aim": {"x": f, "y": f},
  "cooldown": f, "max_cooldown": f,
  "block_meter": f, "block_meter_max": f, "blocking": bool,
  "charging": bool, "charge": f,          // 강공격 (0~60)
  "score": int, "round_wins": int, "coins": int,
  "cards": ["glass_cannon", ...],
  "silenced": bool, "poison": int, "cold": bool
}

BotSnap = { "id","x","y","width","height","hp","max_hp","customization" }

BulletSnap = { "id": int, "x": f, "y": f, "size": f, "owner": str, "color": str }

ZoneSnap = { "type": str, "x": f, "y": f, "radius": f }
// type: heal|toxic|static|emp|frost|implode|shockwave|radiance|chilling

Platform = { "x": f, "y": f, "width": f, "height": f }

CardInfo = { "id","name","desc","category","color","emoji" }
// category: attack|survival|utility|movement|special

ChatMessage = { "sender": str, "text": str, "time": int }   // time = epoch ms

Snapshot = {
  "type": "state", "tick": int, "phase": str, "mode": str,
  "players": [PlayerSnap], "bots": [BotSnap], "bullets": [BulletSnap],
  "zones": [ZoneSnap], "platforms": [Platform],
  "loser_to_pick": str | null,
  "available_cards": [CardInfo],
  "winner_id": str | null
}
```

---

## 4. 게임 규칙 (기존 Node 구현 이식)

- HP 120, 중력 0.6, 마찰 0.8, 이동속도 5, 점프 -16, 기본 쿨다운 15틱.
- 라운드: 상대를 먼저 쓰러뜨리면 `round_wins` +1. **2 라운드 승 = 1 점**, **5 점 = 매치 승리**.
- 라운드 종료 2초 뒤: 점수가 났으면 패자가 카드 5장 중 1장 선택(`picking`), 아니면 즉시 다음 라운드.
- 낙사: `y > HEIGHT + 100` 이면 즉사.
- 가드: `block_meter` 소모, 총알 반사(×-1.35, 소유권 이전).
- 강공격: `strong_start`~`strong_release` 차징(0~60), 발사 후 쿨다운 180틱.
- training 모드: 봇 3마리 유지, 플레이어 사망 시 카드 선택 페이즈.

---

## 5. 백엔드 내부 인터페이스 (모듈 간 계약)

```python
# app/game/models.py  (스캐폴딩 완료, 필드 추가만 허용)
Player, Bot, Bullet, Zone, Room

# app/game/cards.py
CARDS: list[Card]                      # Card(id, name, desc, category, color, emoji, apply)
CARD_BY_ID: dict[str, Card]
def card_infos() -> list[dict]         # REST /api/cards 응답
def random_cards(n: int = 5) -> list[Card]
def apply_card(player: Player, card_id: str) -> bool
def reset_card_state(player: Player) -> None

# app/game/physics.py
def resolve_platform_collision(entity, rect) -> None
def bullet_hits_rect(bullet, rect) -> bool
def apply_explosion(room, x, y, owner_id, damage, radius=90.0, knockback=14.0) -> None
def clamp(v, lo, hi) -> float

# app/game/bullets.py
def spawn_bullet(player: Player, angle: float, **extra) -> Bullet
def update_bullets(room: Room) -> None      # 이동/도탄/명중/폭발 전부 처리

# app/game/bots.py
def create_bot(room: Room) -> Bot
def update_bot(bot: Bot, platforms: list[Platform]) -> None
def respawn_bot(bot: Bot) -> None

# app/game/rooms.py  (RoomManager)
class RoomManager:
    def create(mode, max_players) -> Room
    def get(code) -> Room | None
    def remove(code) -> None
    rooms: dict[str, Room]

# app/game/engine.py
def tick_room(room: Room) -> None        # 1틱 시뮬레이션(플레이어/봇/총알/존/라운드판정)
def snapshot(room: Room) -> dict         # PROTOCOL 3장 Snapshot 그대로

# app/game/serialize.py
def room_state(room: Room) -> dict
```

---

## 6. 코드 규칙

- **파일 하나당 400줄 이내.** 넘으면 모듈을 쪼갠다.
- 백엔드: 순수 게임 로직은 FastAPI/WebSocket 을 import 하지 않는다(테스트 가능하게).
- 프론트: 60Hz 스냅샷은 **React state 로 넣지 않는다**(ref 저장 + canvas 직접 렌더). HUD 등 UI용 값만 ~10Hz 로 store 에 반영.
