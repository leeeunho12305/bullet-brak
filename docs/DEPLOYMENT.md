# 배포 구상

측정 기반 문서다. 아래 숫자는 이 저장소의 실제 코드를 돌려서 나온 값이고, 재측정 방법도 같이 적었다.

---

## 1. 지금 상태 (Phase 0 — 로컬)

```
브라우저 ── :5173 vite dev ──/api·/ws 프록시──> :8000 uvicorn --reload
```

- 로컬 개발은 도커를 쓰지 않는다 (`make dev` = venv + vite). **도커는 배포 전용**이다.
- `make up` → `docker compose up` (배포 스택: nginx 정적 서빙 + `/api`·`/ws` 프록시 → api → postgres, 단일 진입점 :8080)
- **방/매치/플레이어 상태는 전부 프로세스 메모리**다. DB 에는 계정·코인·소유 아이템만 들어간다.

---

## 2. 확장을 가로막는 단 하나의 제약

**방 상태가 프로세스 메모리에 있다.** 그래서 지금 구조는 **API 프로세스를 절대 늘릴 수 없다.**

- `uvicorn --workers 2` 로 띄우면 같은 방 코드로 접속한 두 사람이 서로 다른 워커에 붙는다. 각 워커가 자기만의 `RoomManager` 를 갖고 있어서, 둘 다 "방에 들어왔는데 상대가 안 보이는" 상태가 된다.
- 컨테이너 replica 를 늘려도 동일하다. 로드밸런서가 라운드로빈하면 매 접속마다 다른 방 세계에 떨어진다.
- 그래서 `apps/api/Dockerfile` 은 `--workers 1`, `docker-compose.yml` 은 `replicas: 1` 로 고정해 두었다. **이 두 값을 올리는 것이 가장 흔한 사고 시나리오다.**
- 기동 시 자동 마이그레이션(`DB_AUTO_MIGRATE`)도 인스턴스 1대를 전제한다.

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

- `docker-compose.yml` 앞에 Caddy 를 두고 `bulletbrak.example.com` 을 붙인다 (Caddy 는 WebSocket 을 설정 없이 통과시킨다)
- `restart: unless-stopped` + 헬스체크는 이미 들어있다
- 배포는 `git pull && make up`. **`POSTGRES_PASSWORD` 가 없으면 compose 가 기동을 거부한다.**
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

##### 기본 Build Command 가 `yarn` 인 문제

Render 의 Node 기본 Build Command 는 `yarn` 이다. 그리고 **이 값은 `render.yaml` 로 덮어쓸 수 없다** —
`render.yaml` 은 Blueprint 로 만든 서비스에만 적용되고, 대시보드에서 손으로 만든 서비스는 자기 설정을 쓴다.
(`.node-version` 은 저장소 파일이라 무조건 읽히므로, 로그에 Node 버전만 반영되고 빌드 커맨드는 그대로인 상황이 나온다.)

원래 이 저장소는 `"packageManager": "pnpm@9.15.4"` 때문에 yarn 1 이 실행 즉시 죽었다:

```
error This project's package.json defines "packageManager": "yarn@pnpm@9.15.4".
However the current global version of Yarn is 1.22.22.
```

그래서 대시보드를 못 건드리는 상황에서도 뜨도록 **`yarn` 이 그대로 돌아도 정상 빌드되게** 해뒀다.

1. 루트 `package.json` 에서 `packageManager` 필드를 뺐다 → yarn 1 이 죽지 않는다.
   pnpm 버전은 `engines.pnpm`(`>=9 <10`) + `scripts/render-build.sh` + `apps/web/Dockerfile` + CI 에서 고정한다.
   **이 필드를 다시 넣으면 배포가 도로 깨진다.** package.json 의 `//packageManager` 주석이 그 경고다.
2. `yarn` 이 하는 일은 `yarn install` 하나뿐인데, install 은 `postinstall` 훅을 부른다.
   그 훅([scripts/render-postinstall.mjs](../scripts/render-postinstall.mjs))이 Render 환경일 때만
   실제 빌드(`scripts/render-build.sh`)로 넘긴다. 로컬·CI·도커에서는 즉시 종료한다.
   `render-build.sh` 안의 `pnpm install` 이 같은 훅을 다시 부르므로 `BULLET_BRAK_RENDER_BUILD` 로 재귀를 막는다.
3. Publish Directory 값이 대시보드에 뭘로 잡혀 있는지 알 수 없어서, Render 에서 빌드할 때만
   `apps/web/dist` 를 `dist`, `build`, `apps/web/build` 에도 복사한다(임시 체크아웃에만 생긴다).
4. 서비스가 Static Site 가 아니라 Node Web Service 로 만들어진 경우를 위해 루트에 `start` 스크립트를 뒀다.
   Start Command 기본값 `yarn start` → [scripts/serve-static.mjs](../scripts/serve-static.mjs)(의존성 0,
   SPA 폴백 + `/healthz` + 캐시 헤더)가 `$PORT` 로 `apps/web/dist` 를 서빙한다.

##### 서비스 하나에 프런트와 API 를 같이 태우기

서비스를 새로 만들려면 대시보드를 거쳐야 한다. 그게 불가능할 때를 위해
**Node 서비스 하나에서 FastAPI 를 자식 프로세스로 같이 띄우는** 길을 열어 뒀다.

- 빌드: `scripts/render-build.sh` 가 `python3 -m pip install --user -r apps/api/requirements.txt`
  를 시도한다. python 이나 pip 이 없으면 **빌드를 실패시키지 않고 그냥 넘어간다.**
- 런타임: `scripts/serve-static.mjs` 가 `uvicorn` 을 `127.0.0.1:8001` 에 띄우고
  `/api/health` 가 200 이 될 때까지 최대 20초 기다린 뒤 프록시 대상을 그쪽으로 바꾼다.
- 실패하면 조용히 포기하고 외부 `API_ORIGIN` 프록시로 남는다 —
  즉 **되면 게임이 돌고, 안 되면 지금과 똑같다.** `EMBED_API=0` 으로 끌 수 있다.

Render 의 Node 런타임 이미지에 python3 가 있는지는 보장되지 않으므로 이건 어디까지나
차선책이다. 정석은 아래 Blueprint 로 api 서비스를 따로 만드는 것이다
(방 상태가 프로세스 메모리에 있어 API 를 분리해야 나중에 세로 확장도 쉽다).

##### corepack 이 필드를 되살려 넣는 함정

1번을 해놓고도 런타임에서 이 에러로 죽었다:

```
==> Running 'yarn start'
This project is configured to use pnpm because /opt/render/project/src/package.json has a "packageManager" field
```

**corepack 은 프로젝트에 spec 이 없으면 자기가 하나 써 넣는다(auto-pin).** 소스 그대로다:

```js
console.error(`! The local project doesn't define a 'packageManager' field. Corepack will now add one referencing ...`);
await setLocalPackageManager(path.dirname(result.target), installSpec);
```

빌드 스크립트가 `corepack enable` 을 하니 pnpm 이 corepack shim 으로 잡혔고, 그 shim 이 빌드 도중
`"packageManager": "pnpm@9.15.4"` 를 되살려 넣었다. 그게 산출물과 함께 업로드돼서 런타임의 `yarn start`
가 막힌 것이다. 지운 필드를 우리 빌드가 다시 만든 셈이다. 세 겹으로 막는다.

- **corepack 을 안 쓴다.** `scripts/render-build.sh` 는 pnpm 을 `npm install -g` 로 받고,
  PATH 의 shim 을 피하려고 `$(npm prefix -g)/bin/pnpm` 을 직접 부른다.
- **[.corepack.env](../.corepack.env)** — corepack 이 프로젝트 루트에서 자동으로 읽는다.
  `COREPACK_ENABLE_AUTO_PIN=0`(필드 써넣기 금지) + `COREPACK_ENABLE_STRICT=0`(다른 매니저를 불러도
  예외 대신 실행). 대시보드 환경변수와 달리 **런타임에도 적용된다**.
- **[scripts/strip-package-manager.mjs](../scripts/strip-package-manager.mjs)** — 빌드 마지막에
  혹시 들어온 `packageManager` / `devEngines.packageManager` 를 업로드 전에 지운다.

Blueprint 로 만들면 `render.yaml` 이 `./scripts/render-build.sh` 를 직접 부르므로 위 1~4 는 놀게 된다. 그쪽이 정석이다.
Node 버전은 `.node-version`(22.14.0)으로 고정했다 — CI·Dockerfile 과 같은 메이저다.

정적 사이트와 API 는 서로 다른 오리진이라 아래 두 쌍을 맞춰야 한다. `render.yaml` 에서는
서비스 URL 이 생성 시점에 정해지므로 `sync: false` 로 두고 첫 배포 때 입력한다.

| 서비스 | 환경변수 | 값 |
|---|---|---|
| web | `VITE_API_BASE` | `https://bullet-brak-api.onrender.com` |
| web | `VITE_WS_BASE` | `wss://bullet-brak-api.onrender.com` (https 사이트에서 `ws://` 는 브라우저가 막는다) |
| api | `CORS_ORIGINS` | `https://bullet-brak-web.onrender.com` (끝에 `/` 없이) |

`VITE_*` 는 빌드 타임에 번들에 박히므로, 값을 바꾸면 web 을 **재배포**해야 반영된다.

DB 는 `render.yaml` 의 `databases:` 블록이 api 옆에 같이 뜬다. `DATABASE_URL` 은
`fromDatabase` 로 자동 주입되므로 손으로 넣을 값이 없다. Render 는 드라이버 없는
`postgresql://...` 를 주는데, 서버가 기동할 때 `postgresql+asyncpg://` 로 바꾸고
`sslmode` 파라미터도 정리한다([app/config.py](../apps/api/app/config.py) `normalize_database_url`).
마이그레이션도 기동 시 스스로 돌리므로 Render 쪽에 별도 job 이 필요 없다 — compose 배포와 동작이 같다.

주의할 점:

- **free 플랜은 15분 유휴 시 슬립한다.** 컨테이너가 내려가면 메모리에 있던 방과 WebSocket 이 전부 사라지고,
  다음 접속은 콜드 스타트를 기다린다. 사람을 붙일 거면 `plan: starter` 이상.
- **free 플랜 Postgres 는 생성 후 30일이면 만료돼 삭제된다.** 계정/코인을 실제로 지킬 거면 유료로 올릴 것.
  만료돼도 api 는 죽지 않고 인메모리 모드로 떨어진다(계정 엔드포인트만 503).
- 정적 사이트의 rewrite 규칙으로 `/api`·`/ws` 를 프록시하지 말 것. WebSocket 업그레이드가 통과하지 않는다.
  그래서 nginx 방식(`apps/web/nginx.conf`) 대신 오리진을 분리했다.
- 인스턴스 수는 1개 고정. 이유는 §2. (마이그레이션이 기동 시 도는 것도 이 전제에 기댄다.)

### Phase 2.5 — 셀프 호스팅 (Oracle ARM + Dokploy / Coolify)

`docker-compose.yml` 이 그대로 배포 단위다. api + db + web(nginx) 세 개가 뜬다.
저장소의 유일한 compose 파일이자 유일한 도커 구성이다(개발용 스택은 없다).

1. Dokploy/Coolify 에서 **Compose** 타입 애플리케이션을 만들고 이 저장소를 연결한다.
   Compose 파일 경로는 `docker-compose.yml`.
2. 환경변수를 넣는다. **`POSTGRES_PASSWORD` 는 필수** — 없으면 compose 가 기동을 거부한다
   (기본값을 일부러 안 줬다).

   | 키 | 값 |
   |---|---|
   | `POSTGRES_PASSWORD` | 아무 강한 문자열 (필수) |
   | `CORS_ORIGINS` | 실제 도메인 (예: `https://bulletbrak.example.com`) |
   | `WEB_PROD_PORT` | 리버스 프록시가 붙을 포트 (Dokploy 가 도메인을 붙여주면 기본값 그대로 둬도 된다) |

3. 도메인을 `web` 서비스(80 포트)에 붙인다. `api` 는 `expose` 만 되어 있어 외부로 열리지 않고,
   `db` 는 포트 노출이 아예 없다 — 컨테이너 네트워크 안에서만 붙는다.
4. TLS 를 켠다. **https 페이지에서는 `ws://` 가 막히므로** 프록시가 `wss://` 업그레이드를 통과시켜야 한다.

ARM(Ampere) 관련:

- `postgres:17-alpine`, `python:3.11-slim`, `nginx` 모두 arm64 이미지가 있어 그대로 뜬다.
- `asyncpg` 는 aarch64 휠이 있어 소스 빌드가 일어나지 않는다.

운영 메모:

- 데이터는 `pgdata` 볼륨에 있다. **`docker compose down -v` 는 계정/코인을 통째로 지운다.**
  백업은 `make db-dump > backup.sql`.
- 마이그레이션은 api 가 기동할 때 자동으로 돈다. 배포 파이프라인에 넣을 단계가 없다.
- api 를 2대 이상으로 늘리지 말 것(§2). 방 상태도, 기동 시 마이그레이션도 1대를 전제한다.
  늘려야 하면 `DB_AUTO_MIGRATE=false` 로 끄고 배포 시 한 번만 `make migrate`.

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

### Phase 4 — DB / 계정 (기반 완료, 코인 권위 이전은 진행 중)

Postgres + SQLAlchemy 2.0(async) + Alembic 이 `apps/api/app/db/` 에 붙어 있다.
**DB 는 선택 사항**이라 `DATABASE_URL` 이 비면 예전처럼 인메모리로 뜬다(§README DB 표 참고).

들어간 것:

- **신원** — 익명 계정 + 디바이스 토큰. 로그인 UI 없이 "이 코인이 누구 것인가"에 답할 수 있다.
  토큰은 sha256 해시로만 저장된다. 계약은 [PROTOCOL.md](PROTOCOL.md) §1.1.
- **테이블** — `accounts` / `auth_tokens` / `account_items`.
- **자동 마이그레이션** — 기동 시 `alembic upgrade head`. compose·Render 어디서든 동작이 같다.
- **입장 시 코인 서버 권위화** — WS `join` 에 토큰이 실리면 클라이언트가 신고한 `coins` 를 버리고
  계정 잔액을 쓴다.
- **장애 격리** — DB 연결/마이그레이션이 실패해도 예외를 올리지 않고 인메모리 모드로 계속 뜬다.
  DB 가 죽었다고 게임까지 죽으면 안 된다.

지켜야 하는 것:

- **게임 루프에서 DB 를 건드리지 않는다.** 60Hz 틱에 `await db` 가 끼면 틱이 밀린다.
  DB 접근은 입장(join)·REST·매치 종료 같은 저빈도 지점뿐이다.
  전적 기록용 `accounts.record_match_result()` 도 매치가 **끝난 뒤** 한 번만 부른다.
- 인스턴스는 1대. 기동 시 마이그레이션이 이 전제에 기댄다(늘리면 `DB_AUTO_MIGRATE=false`).

- **구매도 서버 권위** — `POST /api/me/items`. 클라이언트는 아이템 키만 보내고 가격은 서버가 정한다.
  가격 판정과 코인 차감이 한 트랜잭션 안에서 일어나므로 중복 클릭이 이중 결제되지 않는다.

#### 파츠 가격표가 서버로 오는 경로

가격의 단일 진실은 프런트 카탈로그(`apps/web/src/game/avatarParts.ts`)다. 그런데 그 파일은
등급(`tier`)만 적고 **파일 하단에서 tier 기준 안정 정렬**을 하며, 눈 파츠는
눈모양 14 × 눈썹 3 조합으로 생성된다. 즉 **인덱스↔가격 매핑은 정렬 이후에야 확정**되고,
사람이 파이썬으로 옮겨 적으면 반드시 어긋난다(실제로 `eyes:2` 는 소스 순서로는 `Cute`(30원)
자리지만 정렬 후에는 `Round`(0원)다).

그래서 서버용 표는 손으로 쓰지 않고 **생성한다**:

```bash
pnpm shop:prices     # scripts/export-shop-prices.mjs
                     #   -> apps/api/app/game/shop_prices.json (커밋 대상)
```

- 스크립트는 Node 의 타입 스트리핑으로 `avatarParts.ts` 를 그대로 평가한다(번들러/추가 의존성 없음).
  `.node-version`(22.14.0)처럼 기본 활성이 아닌 버전에서는 `--experimental-strip-types` 를 붙여
  자기 자신을 한 번 재실행한다.
- 출력은 결정적이다(키 순서 고정). 두 번 돌려 diff 가 나면 그건 카탈로그가 바뀐 것이다.
- 서버는 `app/game/shop.py` 를 통해 이 JSON 만 본다. 파일이 없거나 깨져도 import 는 살아 있고,
  그 경우 모든 구매가 `invalid_item` 이 된다.

**⚠ 파츠를 추가/삭제하거나 등급을 바꿨으면 `pnpm shop:prices` 를 다시 돌리고 커밋할 것.**
안 돌리면 서버가 옛 가격으로 판정한다. 프런트는 "N코인 필요" 안내 문구에 자기 가격표를 쓰므로,
어긋나면 안내 숫자와 실제 판정이 달라진다.

**아직 남은 것**: 레벨/경험치 보상, 전적·랭킹, 그리고 이관이 끝난 뒤
`ACCOUNT_SEED_COINS_MAX=0` 으로 창구 닫기.

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
- [x] 코인 잔액을 서버 권위로 (WS `join` 이 계정 잔액을 쓴다)
- [x] 구매를 서버 권위로 (`POST /api/me/items`, 가격표는 `pnpm shop:prices` 생성물)
- [ ] 파츠 카탈로그를 바꾼 뒤 `pnpm shop:prices` 재생성을 CI 에서 강제 (지금은 수동 규율)
- [ ] `POSTGRES_PASSWORD` 를 강한 값으로 (`.env.sample` 의 `change-me` 금지)
- [ ] 이관이 끝나면 `ACCOUNT_SEED_COINS_MAX=0` 으로 창구 닫기
- [ ] DB 백업 주기 정하기 (`make db-dump`)
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
