# 배포 구상

측정 기반 문서다. 아래 숫자는 이 저장소의 실제 코드를 돌려서 나온 값이고, 재측정 방법도 같이 적었다.

---

## 1. 지금 상태 (Phase 0 — 로컬)

```
브라우저 ── :5173 vite dev ──/api·/ws 프록시──> :8000 uvicorn --reload
```

- `make up` → `docker compose up` (개발 스택, 소스 마운트 + 핫 리로드)
- `make prod-up` → nginx 가 정적 번들을 서빙하고 `/api`, `/ws` 를 api 컨테이너로 프록시 (단일 진입점 :8080)
- DB 없음. 방/매치/플레이어 상태는 전부 **프로세스 메모리**.

---

## 2. 확장을 가로막는 단 하나의 제약

**방 상태가 프로세스 메모리에 있다.** 그래서 지금 구조는 **API 프로세스를 절대 늘릴 수 없다.**

- `uvicorn --workers 2` 로 띄우면 같은 방 코드로 접속한 두 사람이 서로 다른 워커에 붙는다. 각 워커가 자기만의 `RoomManager` 를 갖고 있어서, 둘 다 "방에 들어왔는데 상대가 안 보이는" 상태가 된다.
- 컨테이너 replica 를 늘려도 동일하다. 로드밸런서가 라운드로빈하면 매 접속마다 다른 방 세계에 떨어진다.
- 그래서 `apps/api/Dockerfile` 은 `--workers 1`, `docker-compose.prod.yml` 은 `replicas: 1` 로 고정해 두었다. **이 두 값을 올리는 것이 가장 흔한 사고 시나리오다.**

세로 확장(더 큰 인스턴스)은 그대로 먹힌다. 가로 확장은 Phase 3 의 방 라우팅이 필요하다.

---

## 3. 측정값과 수용량

재측정:

```bash
cd apps/api
.venv/Scripts/python -m pytest tests -q          # 회귀 확인
# 스냅샷 크기/틱 비용은 아래 스크립트로 (docs 하단 부록)
```

| 항목 | 값 |
|---|---|
| `tick_room` + 직렬화 (2인, 탄환 0) | **0.057 ms** / 틱 (예산 16.67ms 의 0.34%) |
| 2인 + 탄환 16발 | 0.199 ms / 틱 |
| 스냅샷 크기 (일반 틱) | 1,440 B |
| 스냅샷 크기 (0.5초마다 loadout 포함) | 2,323 B |
| **클라이언트 1명당 하향 트래픽** | **약 86 KB/s (≈0.7 Mbps)** |
| 방 1개(2인) | 약 172 KB/s (≈1.4 Mbps) |

### 수용량 추정

| 병목 | 계산 | 한계 |
|---|---|---|
| CPU | 방당 0.057~0.2ms × N < 16.67ms | 이론상 80~290방, 안전하게 **50~80방** (100~160명) |
| 대역폭 | 방당 1.4 Mbps | 100 Mbps 회선 = **약 60방**, 1 Gbps = 약 600방 |
| 메모리 | 방당 수십 KB | 사실상 무시 가능 |

**병목은 CPU 가 아니라 대역폭이 먼저 온다.** 그리고 클라우드에서 대역폭은 곧 요금이다.

- 방 1개를 1시간 돌리면 하향 약 **620 MB**
- AWS/GCP egress 약 $0.09/GB 기준 → **방-시간당 약 $0.06**
- 하루 1,000 방-시간이면 월 egress 만 약 $1,700 → 컴퓨팅 비용보다 훨씬 크다
- Fly.io / Hetzner 처럼 egress 가 싸거나 포함된 곳을 고르는 것이 **인스턴스 스펙보다 중요**하다

### 대역폭을 줄이는 순서 (효과 큰 것부터)

1. **틱레이트 분리**: 시뮬레이션 60Hz 유지, 브로드캐스트 20~30Hz + 클라이언트 보간 → **50~66% 감소**. 렌더러에 이미 보간이 있어서 작업량이 작다. 가장 먼저 할 것.
2. **정적 필드 제거**: `platforms`(230 B, 스냅샷의 10%)는 방마다 고정인데 매 틱 나간다. `room_state` 로 한 번만 보내면 된다. `stats`/`damage_table` 은 이미 0.5초 주기로 낮췄다(38% → 1.3%).
3. **관심 영역/변경분 전송**: 정지한 플레이어·탄환은 매 틱 보낼 필요가 없다. 델타 + 주기적 전체 스냅샷.
4. **바이너리 직렬화**: MessagePack 또는 고정 레이아웃 바이너리 → JSON 대비 40~60% 감소. 좌표를 float64 대신 int16 으로 양자화하면 추가 절감.
5. **압축**: WebSocket permessage-deflate. CPU 를 쓰지만 JSON 은 잘 줄어든다.

1+2 만 해도 클라이언트당 86 → 약 25 KB/s 로 떨어진다.

---

## 4. 단계별 로드맵

### Phase 1 — 단일 VM (동접 ~150명까지)

가장 현실적인 첫 배포. 준비물: VM 1대(2 vCPU / 2GB), 도메인, TLS.

```
인터넷 ──443──> Caddy(자동 TLS) ──> web(nginx, 정적) ──/api·/ws──> api(uvicorn, 단일 프로세스)
```

- `docker-compose.prod.yml` 앞에 Caddy 를 두고 `bulletbrak.example.com` 을 붙인다 (Caddy 는 WebSocket 을 설정 없이 통과시킨다)
- `restart: unless-stopped` + 헬스체크는 이미 들어있다
- 배포는 `git pull && make prod-up`
- **해야 할 일**: 방 생성 rate limit. 지금 `POST /api/rooms` 는 인증도 제한도 없어서 루프 한 줄이면 `MAX_ROOMS`(기본 200)를 즉시 채운다. IP 당 분당 N개로 막을 것.

### Phase 2 — 관리형 PaaS (운영 부담 줄이기)

Fly.io / Render / Railway. 선택 기준은 딱 세 가지다.

1. **WebSocket 유휴 타임아웃** — 라운드 사이에 조용해져도 끊기지 않아야 한다(최소 60초 이상, nginx 설정은 3600초로 잡아둠)
2. **세션 어피니티** — 인스턴스가 2개 이상이면 반드시 필요. 없으면 Phase 3 전까지 인스턴스 1개 고정
3. **egress 요금** — 위 계산 참고. Fly.io 는 지역별 무료 할당이 있어 이 워크로드에 유리하다

#### Render (`render.yaml` 로 정의해 둠)

서비스 2개로 나뉜다. 정적 프런트는 CDN 에서 공짜로 뜨고, API 만 컨테이너로 돈다.

| 서비스 | 타입 | 빌드 | 비고 |
|---|---|---|---|
| `bullet-brak-api` | Docker web service | `apps/api/Dockerfile` (runtime 스테이지) | `PORT=8000`, 헬스체크 `/api/health` |
| `bullet-brak-web` | Static site | `./scripts/render-build.sh` → `apps/web/dist` | SPA rewrite + 캐시 헤더 |

**빌드가 `yarn` 으로 돌면 100% 실패한다.** Render 의 Node 기본 Build Command 가 `yarn` 인데,
yarn 1 은 루트 `package.json` 의 `"packageManager": "pnpm@9.15.4"` 를 보고 Corepack 검사에서 죽는다:

```
error This project's package.json defines "packageManager": "yarn@pnpm@9.15.4".
However the current global version of Yarn is 1.22.22.
```

Blueprint 로 만들면 `render.yaml` 이 알아서 `./scripts/render-build.sh` 를 쓴다.
대시보드에서 손으로 만든 서비스라면 **Settings > Build Command 를 직접 바꿔야 한다** (파일만 커밋해선 안 고쳐진다).
Node 버전은 `.node-version`(22.14.0)으로 고정했다 — CI·Dockerfile 과 같은 메이저다.

정적 사이트와 API 는 서로 다른 오리진이라 아래 두 쌍을 맞춰야 한다. `render.yaml` 에서는
서비스 URL 이 생성 시점에 정해지므로 `sync: false` 로 두고 첫 배포 때 입력한다.

| 서비스 | 환경변수 | 값 |
|---|---|---|
| web | `VITE_API_BASE` | `https://bullet-brak-api.onrender.com` |
| web | `VITE_WS_BASE` | `wss://bullet-brak-api.onrender.com` (https 사이트에서 `ws://` 는 브라우저가 막는다) |
| api | `CORS_ORIGINS` | `https://bullet-brak-web.onrender.com` (끝에 `/` 없이) |

`VITE_*` 는 빌드 타임에 번들에 박히므로, 값을 바꾸면 web 을 **재배포**해야 반영된다.

주의할 점:

- **free 플랜은 15분 유휴 시 슬립한다.** 컨테이너가 내려가면 메모리에 있던 방과 WebSocket 이 전부 사라지고,
  다음 접속은 콜드 스타트를 기다린다. 사람을 붙일 거면 `plan: starter` 이상.
- 정적 사이트의 rewrite 규칙으로 `/api`·`/ws` 를 프록시하지 말 것. WebSocket 업그레이드가 통과하지 않는다.
  그래서 nginx 방식(`apps/web/nginx.conf`) 대신 오리진을 분리했다.
- 인스턴스 수는 1개 고정. 이유는 §2.

### Phase 3 — 가로 확장 (동접 300명 이상)

방을 여러 게임 노드에 나눠 붙이는 단계. 상태를 공유하지 말고 **방을 노드에 고정**하는 것이 정석이다.

```
                 ┌── 매치메이커 (stateless, N대)
브라우저 ── REST ─┤     · 방 생성 요청 → 노드 선택 → Redis 에 {방코드: 노드주소} 기록
                 └──> {code, ws_url: "wss://node-3.example.com/ws/123456"} 응답
브라우저 ── WS ────> 해당 게임 노드에 직접 접속 (이후 통신은 그 노드하고만)
```

- 게임 노드는 지금 코드 그대로. `RoomManager` 를 공유할 필요가 없다
- Redis 에는 방 위치와 노드 부하만 둔다. **게임 상태는 절대 넣지 않는다**(60Hz 로 Redis 를 때리면 그 자체가 병목)
- 노드가 죽으면 그 방들만 소멸 → 클라이언트에 "서버 재시작" 안내 후 로비 복귀
- 필요한 코드 변경: `/api/rooms` 응답에 `ws_url` 추가, 프론트 `net.connect` 가 그 URL 사용. 나머지는 그대로

### Phase 4 — DB 도입

**트리거**: 아래 중 하나라도 필요해지는 순간.

- 계정/로그인, 닉네임 소유
- 코인·레벨·스킨 (지금은 `localStorage` 라서 콘솔에서 숫자만 바꾸면 무한 코인이다)
- 전적, 랭킹, 리플레이

설계:

- Postgres + SQLAlchemy 2.0(async) + Alembic. 자리는 `apps/api/app/db/` 에 비워뒀다
- **게임 루프에서 DB 를 건드리지 않는다.** 매치 종료 시점에만 결과를 비동기 큐로 넘겨 기록한다. 60Hz 루프에 await DB 가 끼면 틱이 밀린다
- `docker-compose.prod.yml` 하단에 db 서비스 주석이 준비돼 있다

### Phase 5 — 관측과 운영

- **틱 지연 히스토그램**이 이 게임의 핵심 지표다. `tick_room` 소요시간과 목표 대비 드리프트를 Prometheus 로 노출 → 16.67ms 를 넘기 시작하면 그때가 노드 증설 시점
- 방 수, 동접 수, 방당 평균 수명, 스냅샷 바이트/초
- Sentry(프론트 에러), 구조화 로그(JSON) + Loki
- 부하 테스트: 봇 클라이언트 N개를 붙이는 스크립트(`websockets` 로 40줄이면 된다)로 실제 한계를 확인한 뒤 Phase 3 를 결정한다

---

## 5. 배포 전 체크리스트

- [ ] `POST /api/rooms` rate limit (지금 무제한 — 가장 시급)
- [ ] WebSocket 메시지 크기/빈도 제한 (채팅 스팸, 거대 페이로드)
- [ ] `CORS_ORIGINS` 를 실제 도메인으로 (개발 기본값이 localhost)
- [ ] `DEBUG=false`
- [ ] 코인을 서버 권위로 이전 (Phase 4 와 함께)
- [ ] 방 자동 정리 동작 확인 (`ROOM_IDLE_TIMEOUT_SEC`, 기본 300초)
- [ ] TLS + `wss://` (혼합 콘텐츠면 브라우저가 WS 를 막는다)
- [ ] 컨테이너 non-root 실행 (api 는 적용됨, nginx 이미지는 기본 설정 사용)

---

## 부록 — 측정 스크립트

```python
# apps/api 에서 .venv/Scripts/python 으로 실행
import json
from app.game.rooms import RoomManager
from app.game.models import Player
from app.game.serialize import snapshot, LOADOUT_INTERVAL

room = RoomManager().create("pvp", 2)
for i, pid in enumerate(("a", "b")):
    room.players[pid] = Player(id=pid, nickname="플레이어", x=100.0 + i * 400)
room.phase = "playing"

room.tick = 1
slim = len(json.dumps(snapshot(room), ensure_ascii=False).encode())
room.tick = LOADOUT_INTERVAL
full = len(json.dumps(snapshot(room), ensure_ascii=False).encode())
avg = (slim * (LOADOUT_INTERVAL - 1) + full) / LOADOUT_INTERVAL
print(f"평균 {avg:,.0f}B/틱 -> 클라 1명당 {avg * 60 / 1024:.0f} KB/s")
```
