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
| GET | `/api/health` | - | `{"status":"ok","db":"on"\|"off"}` — DB 상태와 무관하게 항상 200 |
| POST | `/api/rooms` | `{"mode":"pvp"\|"training","max_players":2,"map_id":"classic"}` | `{"code":"123456","mode":"pvp","max_players":2,"map_id":"classic"}` |
| GET | `/api/rooms/{code}` | - | `{"code","mode","max_players","player_count","phase","map_id"}` / 404 `{"detail":"..."}` |
| GET | `/api/cards` | - | `[{"id","name","desc","category","color","emoji"}]` |
| GET | `/api/maps` | - | `[MapInfo]` — 발판·스폰·테마까지. 대기실 미리보기가 그대로 그린다 |

`mode`: `pvp`(방 대전) / `training`(봇 3마리 솔로 연습).

`map_id`: 맵 id 또는 `"random"`. 모르는 값이면 서버가 기본 맵(`classic`)으로 되돌린다.
`"random"` 이면 **라운드마다** 맵이 바뀐다(훈련장은 낙사 없는 맵 중에서만 뽑는다).

### 1.1 계정 (`/api/auth`, `/api/me`)

**신원의 단위는 언제나 디바이스 토큰이다.** 브라우저가 불투명 난수 하나를
`localStorage.bulletBrakToken` 에 들고 있고, 서버는 그 sha256 해시로 계정을 찾는다.
평문 토큰은 서버에 저장되지 않는다.

앱을 처음 열면 **익명 계정이 자동으로 생긴다**(회원가입 화면이 없다). 로그인 수단은
그 위에 나중에 얹는 선택지이며, 어느 경로로 로그인하든 결과물은 똑같이
"이 기기의 디바이스 토큰 한 개"다 — 세션도 쿠키도 없고, **WS 입장 경로는 전혀 바뀌지 않는다.**

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/auth/anon` | - | `{"nickname":str,"customization":Customization,"seed_coins":int,"seed_items":[str]}` | 201 `{"token":str,"account":Account}` |
| POST | `/api/auth/login` | - | `{"login_id":str,"password":str}` | `AuthResult` |
| POST | `/api/auth/redeem` | - | `{"code":str}` | `AuthResult` |
| GET | `/api/me` | Bearer | - | `Account` |
| PATCH | `/api/me` | Bearer | `{"nickname"?:str,"customization"?:Customization}` | `Account` |
| POST | `/api/me/credentials` | Bearer | `{"login_id":str,"password":str}` | `{"ok":bool,"reason":str,"login_id":str\|null,"message":str}` |
| POST | `/api/me/recovery-code` | Bearer | - | 201 `{"code":str,"issued_at":datetime}` |
| POST | `/api/me/items` | Bearer | `{"item_key":str}` | `{"ok":bool,"reason":str,"coins":int,"owned_items":[str]}` |

```jsonc
// Account
{
  "id": "ed2845fa7e654d48b66ff246718ed2bf",
  "nickname": "테스터",
  "customization": { /* Customization */ },
  "coins": 250,          // 서버 권위. PATCH 로 바꿀 수 없다
  "level": 1, "xp": 0,
  "matches_played": 0, "matches_won": 0,
  "owned_items": ["eyes:3"],
  "login_id": "minsu99",     // null 이면 아직 이 기기에만 묶인 계정
  "has_recovery_code": true  // 있다/없다만. 코드 평문은 절대 여기 실리지 않는다
}

// AuthResult — 로그인(/auth/login)과 인계 코드(/auth/redeem)의 공통 응답
{ "ok": true,  "reason": "ok", "token": "...", "account": { /* Account */ } }
{ "ok": false, "reason": "invalid_credentials", "token": null, "account": null }
```

- 토큰은 `Authorization: Bearer <token>` 헤더로만 보낸다. **쿼리스트링에 싣지 않는다**(액세스 로그에 남는다).
- `token` 평문은 응답에서 **한 번만** 나온다. 잃어도 아이디나 인계 코드가 있으면 되찾을 수 있다.
- `seed_coins` / `seed_items` 는 localStorage 시절 잔액·소유를 물려받기 위한 값이다.
  위조 가능한 값이라 `ACCOUNT_SEED_COINS_MAX` 로 잘린다. 이관이 끝나면 0 으로 내린다.
- **서버에 DB 가 없으면 이 엔드포인트들은 503** 을 돌려준다. 클라이언트는 그때 예전처럼
  localStorage 로만 동작한다(`GET /api/health` 의 `db` 로 미리 알 수 있다).

#### 로그인 (`POST /api/auth/login`, `POST /api/me/credentials`)

```jsonc
// 1) 아이디/비밀번호 만들기 — 지금 쓰던 계정에 얹는다(승격). 새 계정이 아니라서 코인이 따라온다.
POST /api/me/credentials   { "login_id": "minsu99", "password": "..." }
{ "ok": true, "reason": "ok", "login_id": "minsu99", "message": "아이디와 비밀번호를 저장했어요." }

// 2) 다른 기기에서 로그인 — 토큰이 하나도 없는 상태에서 부를 수 있다.
POST /api/auth/login       { "login_id": "MINSU99", "password": "..." }
{ "ok": true, "reason": "ok", "token": "<이 기기의 새 디바이스 토큰>", "account": { ... } }
```

- **아이디는 대소문자를 구분하지 않는다.** 영문 소문자로 시작하는 4~20자(소문자·숫자·밑줄)로
  정규화해 저장하고 조회한다.
- 비밀번호는 bcrypt 해시로만 저장한다. **해싱은 워커 스레드에서 돈다** —
  이 프로세스의 이벤트 루프는 60Hz 틱 루프와 같은 루프라, 동기로 해싱하면 틱이 밀린다
  (`app/services/passwords.py`).
- 실패 사유는 `invalid_credentials` 하나로 뭉뚱그린다. "아이디 없음"과 "비번 틀림"을
  나누면 그 창구가 **아이디 존재 여부를 알려주는 도구**가 된다. 없는 아이디에도 더미 해시로
  대조해 응답 시간까지 맞춘다.
- 로그인은 기존 토큰을 회수하지 않는다. 기기 여러 대가 동시에 붙어 있는 게 정상이다.
- `/auth/login` 과 `/auth/redeem` 은 **IP 기준 10분 10회**로 제한된다. 초과하면 429 +
  `Retry-After` 헤더다(200 + ok:false 가 아니다 — 차단은 정상 결과가 아니다).

#### 인계 코드 (`POST /api/me/recovery-code`, `POST /api/auth/redeem`)

비밀번호를 잊었을 때의 우회로다. 이메일이 없는 구조라 복구 경로가 하나는 있어야 한다.

```jsonc
POST /api/me/recovery-code        // -> 201
{ "code": "K7M2-9QPX-3W5B", "issued_at": "2026-08-21T09:00:00Z" }

POST /api/auth/redeem   { "code": "k7m2 9qpx 3w5b" }   // 하이픈·대소문자 상관없음
{ "ok": true, "reason": "ok", "token": "...", "account": { ... } }
```

- 코드는 Crockford Base32 12자(≈60비트)다. 알파벳에 `I·L·O·U` 가 없고, 입력할 때
  `O→0` / `I·L→1` 로 되돌려 준다 — 사람이 옮겨 적는 물건이기 때문이다.
- **평문은 발급 응답에서만 나온다.** 서버는 sha256 해시만 갖고 있어서 다시 보여줄 방법이 없다.
  `Account.has_recovery_code` 로 있다/없다만 알 수 있다.
- **소모되지 않는다** — 기기를 셋, 넷 붙일 수 있어야 한다.
- 계정당 하나다. 재발급하면 **이전 코드는 그 즉시 죽는다.** 그게 곧 유출됐을 때의 폐기 수단이다.

#### 구매 (`POST /api/me/items`)

```jsonc
// 요청 — 아이템 키 하나가 전부다.
{ "item_key": "eyes:8" }

// 응답 (항상 200). 거절도 예외가 아니라 정상 응답이다.
{ "ok": false, "reason": "insufficient_coins", "coins": 70, "owned_items": ["eyes:3"] }
```

- `item_key` 는 `"{category}:{index}"`. category 는 `eyes|mouths|details|details2`.
  `colors` 는 항상 무료라 구매 대상이 아니다(`invalid_item`).
  `eyes:08` 같은 별칭 표기는 거절한다 — 같은 파츠를 두 번 팔지 않기 위해서다.
- `reason`: `ok` | `already_owned` | `insufficient_coins` | `invalid_item`.
  (형식이 아예 틀리거나 필드가 없으면 pydantic 422 — 위 4가지 밖이다.)
- **가격은 서버가 정한다.** 요청 본문에 `price`/`coins` 를 끼워 넣어도 무시된다.
  서버 가격표는 `apps/api/app/game/shop_prices.json` 이고 프런트 카탈로그에서 생성된다
  (`pnpm shop:prices` — 자세한 건 DEPLOYMENT.md Phase 4).
- `coins`/`owned_items` 는 **구매 후 확정 상태**다. 클라이언트는 그대로 덮어쓰면 된다.

---

## 2. WebSocket

접속: `ws://<host>/ws/{code}?nickname=<닉>`

접속 직후 클라이언트가 **반드시** `join` 을 1회 보낸다. 서버는 `welcome` 으로 응답한다.
방이 없거나 가득 찼으면 서버는 `error` 를 보내고 close(코드 4404 / 4409).

### 2.1 Client → Server

| type | payload | 설명 |
|---|---|---|
| `join` | `{"nickname":str,"customization":Customization,"coins":int,"token"?:str}` | 입장(최초 1회). `token` 이 유효하면 서버가 `coins` 를 무시하고 **계정 잔액**을 쓴다. WS 는 헤더를 못 붙이므로 토큰을 본문으로 받는다 |
| `input` | `{"left":bool,"right":bool,"jump":bool,"block":bool}` | 이동/가드 입력 (변경 시에만 전송) |
| `aim` | `{"x":float,"y":float}` | 마우스 월드 좌표 (최대 30Hz 스로틀) |
| `shoot` | `{}` | 일반 사격 |
| `strong_start` | `{}` | 강공격 차징 시작 |
| `strong_release` | `{}` | 강공격 발사 |
| `pick_card` | `{"card_id":str}` | 카드 선택 (패자만 유효) |
| `open_cards` | `{}` | **훈련장 전용.** 싸우는 중에 카드 목록을 직접 연다. 대전 방·사망 중·웨이브 사이에서는 서버가 무시한다 |
| `chat` | `{"text":str}` | 채팅 (서버에서 200자 제한만 적용) |
| `set_map` | `{"map_id":str}` | 방장이 맵 선택 (`waiting`/`finished` 에서만, 방장 아니면 무시). 편집한 배치는 버려진다 |
| `set_platforms` | `{"platforms":[Platform]}` | 방장의 맵 에디터 저장. 서버가 좌표/종류를 다시 검증하고 못 쓰는 항목은 버린다 (최대 160개, 빈 배치는 거절) |
| `reset_platforms` | `{}` | 편집한 배치를 버리고 맵 원본 지형으로 (방장 전용) |
| `start_game` | `{}` | 방장이 게임 시작 |
| `restart` | `{}` | 종료 후 대기실로 되돌리기 |
| `rematch` | `{"accept":bool}` | 종료 후 "한 판 더?" 투표. 전원 동의 시 즉시 새 매치, 한 명이라도 거절하면 대기실로 |
| `avatar` | `{"customization":Customization}` | 대기 중 외형 변경 |

### 2.2 Server → Client

| type | payload |
|---|---|
| `welcome` | `{"player_id":str,"account_id":str\|null,"room":RoomState}` — `account_id` 가 null 이면 비로그인(이번 판 진행이 저장되지 않는다) |
| `room_state` | `{"room":RoomState}` |
| `state` | `Snapshot` (60Hz) |
| `chat` | `{"message":ChatMessage}` |
| `event` | `{"event":"round_over"\|"match_over"\|"card_phase"\|"game_started","winner_id":str\|null,"loser_id":str\|null}` |
| `player_left` | `{"player_id":str,"nickname":str,"players_left":int}` — 남은 사람에게만. 뒤이어 오는 `room_state` 보다 **먼저** 보낸다 |
| `error` | `{"message":str}` |

`player_left`: 2인 방에서 한 명이 나가면 서버가 매치를 접고 `phase` 를 `waiting` 으로 되돌린다.
남은 사람 입장에서는 화면이 갑자기 대기실로 바뀌므로, 그 이유를 알리는 메시지가 반드시 필요하다.

---

## 3. 데이터 구조 (JSON)

```jsonc
Customization = {
  "eye": 0, "mouth": 0, "detail": 0, "detail2": 0,   // 파츠 index (편집기 탭 4개)
  "color": "#ff6b6b",
  "offsets": { "eye": {"x": 0.05, "y": -0.02} }      // 파츠 위치 보정(몸통 대비 비율, ±0.32)
}
// offsets 는 0이 아닌 슬롯만 실린다. 모르는 슬롯/범위 밖 값은 서버가 버린다.
// detail  = DETAIL1(얼굴 디테일), detail2 = DETAIL2(머리 위 액세서리)

MapTheme = { "bg": "#0b0d17", "grid": "rgba(...)", "platform": "#1b2438", "edge": "rgba(...)" }

MapInfo = {
  "id": "classic", "name": "클래식", "emoji": "🟦", "desc": "...",
  "theme": MapTheme,
  "platforms": [Platform],          // 인게임과 같은 800x600 좌표계
  "spawns": [ {"x": f, "y": f} ]    // 라운드 시작 위치(플레이어 수만큼 나눠 쓴다)
}

RoomState = {
  "code": "123456", "mode": "pvp", "max_players": 2, "phase": "waiting",
  "map_id": "random",               // 방장이 고른 값. "random" 일 수 있다
  "map": MapInfo,                   // 지금 실제로 깔려 있는 맵(platforms 는 편집 결과가 반영된 값)
  "custom_map": false,              // 발판이 맵 원본이 아니라 방장이 에디터로 짠 배치인가
  "players": [ { "id": "...", "nickname": "익명", "customization": Customization, "coins": 0 } ]
}
// phase: "waiting" | "playing" | "round_over" | "picking" | "finished"
// 맵이 바뀌면(무작위 리롤 포함) 서버가 room_state 를 한 번 더 브로드캐스트한다.
// 테마/이름을 60Hz 스냅샷에 싣지 않기 위한 장치다.

PlayerSnap = {
  "id": str, "nickname": str, "customization": Customization,
  "x": f, "y": f, "width": f, "height": f, "vx": f, "vy": f,
  "hp": f, "max_hp": f, "alive": bool,
  "aim": {"x": f, "y": f},
  "cooldown": f, "max_cooldown": f,
  // 가드는 게이지가 아니라 "라운드당 남은 횟수"다(§4 참고).
  "block_meter": f, "block_meter_max": f,     // 남은 가드 게이지 / 라운드당 최대치(150)
  "blocking": bool,
  "charging": bool, "charge": f,          // 강공격 (0~60)
  "score": int, "round_wins": int, "coins": int,
  "cards": ["glass_cannon", ...],
  "silenced": bool, "poison": int, "cold": bool, "stunned": bool,
  "windup": f,                            // 정지 충전 게이지(0~60). WIND UP / CAREFUL
                                          // PLANNING / RITUAL COUNTDOWN 이 쓴다
  // Tab 오버레이용 — 아래 두 필드는 대전 중 0.5초(30틱)에 한 번만 실린다.
  // 없는 틱에는 클라이언트가 마지막으로 받은 값을 그대로 유지한다.
  "stats": { "damage_mult","max_hp","speed","cooldown","bullet_speed","bullet_size",
             "bounces","knockback","block_meter","block_seconds","shots_per_fire" },  // 전부 number, optional
  "damage_table": [ { "distance": 0, "damage": 30.0 }, ... ]  // 0,100,200,400,600,800px, optional
}

BotSnap = { "id","x","y","width","height","hp","max_hp","customization",
            "silenced","poison","cold","stunned",   // 봇도 플레이어와 같은 상태이상을 받는다
            "tier": "dummy"|"rookie"|"veteran",   // 난이도. 클라가 이름표/테두리로 구분
            "aim": {"x": f, "y": f} }             // 봇이 겨누는 지점(허수아비는 자기 위치)

BulletSnap = { "id": int, "x": f, "y": f, "size": f, "owner": str, "color": str }

ZoneSnap = { "type": str, "x": f, "y": f, "radius": f, "d": int }
// type: heal|toxic|static|emp|frost|implode|shockwave|radiance|chilling|blast
// d   : 남은 틱. blast(폭발 섬광)의 퍼지는 정도를 클라가 이 값으로 그린다
// blast 는 apply_explosion 이 남기는 **연출 전용** 장판이다(sim.EFFECT_ZONES).
//       BLAST_TICKS(12틱) 동안만 살아 있고 누구에게도 효과를 주지 않는다.
// heal/radiance 는 소유자에게만 적용된다(sim.OWNER_ONLY_ZONES).

Platform = {
  "x": f, "y": f, "width": f, "height": f,
  "type": "jump",                   // 생략되면 "solid". solid|jump|mover|ice|hazard
  "power": f,                       // jump 만: 위로 튀는 속도
  "axis": "x"                       // mover 만: 왕복 축 ("x" | "y")
}
// 블럭 효과(app/game/blocks.py)
//   solid  일반 블럭 — 위/아래/옆 전부 막힌다
//   jump   점프대   — 실체가 없다(blocks.PASSABLE). 바닥 윗면과 같은 높이로 깔고,
//                    지나가면 power 만큼 튀며 공중 점프가 다시 찬다. 탄환도 통과한다
//   mover  이동발판 — 축을 따라 왕복하고, 올라탄 사람을 같이 나른다
//   ice    빙판     — 마찰이 거의 없다
//   hazard 가시     — 밟을 때마다 HAZARD_DAMAGE(50) 를 깎고 튕겨낸다.
//                    HAZARD_GRACE(45틱) 동안은 다시 아프지 않다(한 번 밟음 = 한 번 피해)
// span/speed/phase/ox/oy 는 서버 내부 값이라 스냅샷에 실리지 않는다
// (에디터가 set_platforms 로 보낼 때만 span/speed 를 쓴다).

CardInfo = { "id","name","desc","category","color","emoji" }
// category: attack|survival|utility|movement|special

ChatMessage = { "sender": str, "text": str, "time": int }   // time = epoch ms

TrainingSnap = {              // mode=="training" 일 때만. pvp 면 null
  "wave": int,                // 현재 웨이브(1부터)
  "bots_left": int, "wave_bots": int,
  "state": "fighting" | "wave_clear" | "respawning",
  "timer": int,               // 다음 전환까지 남은 틱(0이면 카운트다운 없음)
  "kills": int, "deaths": int, "best_wave": int,
  "shots": int, "hits": int,  // 명중률 = hits/shots (클라가 계산)
  "damage_dealt": f, "damage_taken": f,
  "survived_ticks": int       // 현재 목숨의 생존 틱
}

Snapshot = {
  "type": "state", "tick": int, "phase": str, "mode": str,
  "map_id": str,                    // 지금 깔린 맵. 이름/테마는 RoomState 로만 온다
  "players": [PlayerSnap], "bots": [BotSnap], "bullets": [BulletSnap],
  "zones": [ZoneSnap],
  "platforms": [Platform],          // LAYOUT_INTERVAL(30틱)마다 · 대기 중에는 매 틱. 없으면 직전 값을 쓴다
  "movers": [{"i": int, "x": f, "y": f}],  // 그 사이 틱의 이동발판 좌표만(i = platforms 인덱스). 없으면 생략
  "loser_to_pick": str | null,
  "available_cards": [CardInfo],
  "winner_id": str | null,
  "rematch": [str],                 // 리매치에 동의한 player id. finished 에서만 찬다
  "training": TrainingSnap | null
}
```

---

## 4. 게임 규칙 (기존 Node 구현 이식)

- HP 120, 중력 0.6, 마찰 0.8, 이동속도 5, 점프 -16, 기본 쿨다운 15틱.
- 라운드: 상대를 먼저 쓰러뜨리면 `round_wins` +1. **2 라운드 승 = 1 점**, **5 점 = 매치 승리**.
- 라운드 종료 2초 뒤: 점수가 났으면 패자가 카드 5장 중 1장 선택(`picking`), 아니면 즉시 다음 라운드.
- 매치 종료(`finished`) 후 리매치: 양쪽 다 `rematch{accept:true}` 를 보내면 카드/스탯을 초기화하고
  대기실을 거치지 않고 바로 `playing` 으로 간다. 한 명이라도 거절하면 `waiting`(대기실)으로 돌아간다.
- **거리별 대미지 감쇠**: 탄환이 발사 지점에서 날아간 거리에 비례해 위력이 줄어든다.
  배율 = 0px 에서 1.5배 → 600px 이상 0.4배 (선형). 기본 탄(20) 기준 근접 30 / 원거리 8.
  가드 반사 시 반사 지점이 새 기준점이 되고, 위력은 반사한 쪽 공격력 배율로 환산된다.
  공격력 배율은 **발사 시점에 한 번만** 적용한다(명중 시 재적용 금지).
  **산탄(BUCKSHOT) 탄알은 곡선이 따로다** — `SCATTER_FALLOFF_RANGE`(260px)에서 0.15배까지
  떨어진다. 알이 네 개라 근접 합계가 크므로, 거리로 값을 치르게 한다.
- 월드 경계: 좌우 벽과 **천장(`y = 0`)은 막혀 있다**(플레이어/봇 모두 `vy` 가 0으로 끊긴다).
  탄환도 이 세 면에서만 튕긴다. **바닥은 뚫려 있고, 그리로 나간 탄환은 튕기지 않고 사라진다** —
  협곡·부유섬의 허공에서 벽도 없이 되돌아오면 안 된다.
- **도탄**: 벽이나 발판에 튕길 때마다 `life` 가 `life_max` 로 초기화된다. 그래야 도탄 카드를
  여러 장 겹쳤을 때 수명이 먼저 끝나지 않고 실제로 그 횟수만큼 튕긴다.
  **가드 반사는 도탄으로 세지 않는다**(`bounces` 를 올리지 않고 수명만 되돌린다).
- **넉백**: `apply_knockback` 하나로만 준다. 수평은 `Bullet.knockback × KNOCKBACK_SCALE` 이고,
  이동 속도를 넘는 부분은 clamp/마찰이 지우지 않고 `KNOCKBACK_DECAY` 로 천천히 식는다.
  위로 뜨는 양만 `MAX_HIT_LIFT`(9)로 묶는다 — 산탄·연발이 겹쳐도 점프(16)보다 높이 솟지 않는다.
- 낙사: `y > HEIGHT + 100` 이면 즉사.
- 가드: **라운드당 게이지**다(`BLOCK_METER_MAX` = 150, DEFENDER 가 +75).
  누르고 있는 동안만 `BLOCK_DRAIN`(= 150 / 30초 / 60틱) 씩 줄고, 손을 떼면 그 자리에서 멈춘다 —
  언제든 끊었다 다시 쓸 수 있다. 가득 찬 게이지를 계속 눌러 다 쓰면 `BLOCK_DRAIN_SECONDS`(30초).
  SHIELDS UP 은 `block_drain` 을 ×0.7 로 줄인다(같은 게이지로 약 43초).
  라운드 안에서는 회복되지 않고, `reset_round`(훈련장은 `start_wave`/부활)에서만 채워진다.
  펼쳐진 동안 닿은 총알은 반사된다(×-1.35, 소유권 이전, 수명 초기화). 가드 장판과 톱날은
  **가드를 시작한 틱에 한 번만** 생성된다.
- 폭발(`apply_explosion`)은 **터뜨린 본인에게는 닿지 않는다**. 연출용 `blast` 장판을 남긴다.
- 강공격: `strong_start`~`strong_release` 차징(0~60), 발사 후 쿨다운 180틱.
- **training 모드(훈련장)**: 웨이브 방식. 라운드/점수/매치 승리가 없다.
  - 웨이브마다 정해진 구성의 봇이 스폰된다. 봇 티어는 3종:
    `dummy`(움직이기만 하는 허수아비) / `rookie`(느리게 조준해 사격) / `veteran`(선도 사격 + 회피).
  - 봇은 서로를 쏘지 않는다(같은 봇 소유 탄환은 봇에게 명중 판정하지 않는다).
    봇은 시야가 막히면(플랫폼이 가로막으면) 쏘지 않는다.
  - 웨이브 전멸 → `wave_clear`(1.5초) → `picking` → 다음 웨이브.
  - **카드는 전부 열린다.** 대전은 무작위 5장이지만 훈련장은 `available_cards` 에 카드 전체가
    실린다(`engine.open_card_pick`). 시험해 보는 곳이지 이기는 곳이 아니기 때문이다.
    클라이언트는 8장을 넘으면 뒤집기 카드 대신 검색되는 목록으로 그린다.
  - 싸우는 중에도 `open_cards` 로 직접 열 수 있다. 그렇게 고른 카드는 웨이브를 넘기지 않고
    하던 판을 그대로 이어 간다(`training.resume_after_pick`).
  - 플레이어 사망 → `respawning`(3초) → 같은 웨이브를 처음부터. 카드와 스탯은 유지한다.
    `deaths` 만 올라가고 매치는 끝나지 않는다.
  - 통계(킬/사망/명중률/누적 대미지/최고 웨이브/생존 시간)는 `Snapshot.training` 으로 내려간다.

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
def all_card_ids() -> list[str]         # 훈련장 카드 창(전부 열어 준다)
def apply_card(player: Player, card_id: str) -> bool
def reset_card_state(player: Player) -> None

# app/game/physics.py
def resolve_platform_collision(entity, rect) -> None
def bullet_hits_rect(bullet, rect) -> bool
def apply_explosion(room, x, y, owner_id, damage, radius=90.0, knockback=14.0) -> None
def apply_knockback(entity, dx, dy, power, lift=..., pop=...) -> None  # 넉백의 유일한 창구
def clamp(v, lo, hi) -> float

# app/game/bullets.py
def spawn_bullet(player: Player, angle: float, **extra) -> Bullet
def update_bullets(room: Room) -> None      # 이동/도탄/명중/폭발 전부 처리

# app/game/bots.py   (훈련장 전투 AI)
def create_bot(room: Room, tier: str = "rookie") -> Bot
def update_bot(room: Room, bot: Bot) -> None    # 조준/사격/회피/이동 1틱
def kill_bot(bot: Bot) -> None                  # hp=0 (제거는 training 이 담당)

# app/game/training.py   (훈련장 진행/통계. training 모드에서만 동작)
def ensure(room: Room) -> TrainingState | None  # 훈련방이면 상태를 만들어 돌려준다
def tick(room: Room) -> None                    # 웨이브 전멸/사망 판정 + 카운트다운
def start_wave(room: Room, wave: int) -> None
def record(room: Room, key: str, amount: float = 1) -> None   # 통계 집계(no-op 가능)
def snap(room: Room) -> dict | None             # PROTOCOL 3장 TrainingSnap

# app/game/maps.py  (맵 카탈로그 — constants 외에 아무것도 import 하지 않는다)
RANDOM_ID = "random"; DEFAULT_ID = "classic"
BY_ID: dict[str, GameMap]                       # 발판/스폰/테마를 든 불변 데이터
TRAINING_SAFE_IDS: tuple[str, ...]              # 낙사 없는 맵(훈련장 무작위용)
def catalog() -> list[dict]                     # GET /api/maps
def get(map_id) -> GameMap                      # 모르는 id 면 기본 맵
def is_valid_selection(map_id) -> bool          # 실제 맵이거나 "random"
def resolve(map_id, current=None) -> str        # "random" -> 실제 id
def apply(room, map_id) -> GameMap              # 방에 발판을 깔고 active_map_id 기록
                                                # room.custom_layout 이 있으면 그걸 우선 깐다
def rect/jump/mover/ice/spike(...) -> Rect      # 블럭 생성자(app.game.blocks 위임)

# app/game/blocks.py  (블럭 종류와 효과 — constants 외에 아무것도 import 하지 않는다)
TYPES = ("solid", "jump", "mover", "ice", "hazard"); PASSABLE = {"jump"}; MAX_BLOCKS = 160
def make(x, y, w, h, kind="solid", **opts) -> Rect   # 종류별 기본값을 채운 블럭
def normalize_all(raw) -> list[Rect]                 # 클라이언트 페이로드 검증
def snap(block) -> Rect                              # 스냅샷용(내부 필드 제외)
def update_movers(room) -> None                      # 엔티티 물리보다 먼저 호출한다
def carry(entity, room) -> None                      # 올라탄 이동발판을 따라간다
def is_solid(block) -> bool                          # False 면 밀어내지 않는다(점프대)
def touch(entity, block) -> bool                     # 실체 없는 블럭 효과(점프대 발동)
def on_contact(entity, block, side, index) -> float  # 충돌 직후 효과. 입은 피해를 반환
def spawn_points(room=None) -> list[tuple[float, float]]
                                                # room 을 주면 가시 위 스폰을 옆으로 밀어낸다

# app/game/rooms.py  (RoomManager)
class RoomManager:
    def create(mode, max_players, map_id="classic") -> Room
    def get(code) -> Room | None
    def remove(code) -> None
    rooms: dict[str, Room]

# app/game/engine.py
def tick_room(room: Room) -> None        # 1틱 시뮬레이션(플레이어/봇/총알/존/라운드판정)
def snapshot(room: Room) -> dict         # PROTOCOL 3장 Snapshot 그대로
def set_map(room, map_id) -> bool        # 방장 선택(waiting/finished 에서만). custom_layout 을 버린다
def set_platforms(room, raw) -> bool     # 맵 에디터 저장(검증은 blocks.normalize_all)
def clear_platforms(room) -> bool        # 맵 원본 지형으로 되돌리기
def prepare_map(room) -> None            # 라운드 시작 전 맵 확정("random" 이면 리롤)

# app/game/serialize.py
def room_state(room: Room) -> dict
```

---

## 6. 코드 규칙

- **파일 하나당 400줄 이내.** 넘으면 모듈을 쪼갠다.
- 백엔드: 순수 게임 로직은 FastAPI/WebSocket 을 import 하지 않는다(테스트 가능하게).
- 프론트: 60Hz 스냅샷은 **React state 로 넣지 않는다**(ref 저장 + canvas 직접 렌더). HUD 등 UI용 값만 ~10Hz 로 store 에 반영.
