# Bullet Brak

ROUNDS 스타일 2D PvP 물리 슈팅 게임. **FastAPI(서버 권위 60Hz 시뮬레이션) + React 19(Vite + TypeScript)** 모노레포.

- 라운드 2승 = 1점, 먼저 5점을 내면 매치 승리
- 라운드에서 진 쪽이 카드 5장 중 1장을 골라 빌드를 쌓는다 (카드 67종)
- 물리 기반 전투: 넉백, 낙사, 도탄, 폭발, 가드 반사, 거리별 대미지 감쇠

---

## 빠른 시작

도커도 make 도 필요 없다. **Node 20+ 와 Python 3.11+** 만 있으면 된다.

```bash
corepack enable pnpm     # pnpm 이 없을 때만 (관리자 권한이 필요할 수 있다)
pnpm bootstrap           # 프론트 의존성 + 백엔드 venv 를 한 번에
pnpm dev                 # api(:8000) + web(:5173) 를 한 터미널에서 (Ctrl+C 로 둘 다 종료)
```

> `pnpm setup` 은 pnpm 의 내장 명령(PNPM_HOME/PATH 설정)이라 package.json 스크립트가 실행되지
> 않는다. 그래서 이 저장소의 설치 스크립트 이름은 `bootstrap` 이다.

브라우저는 **http://localhost:5173** 하나만 보면 된다. vite dev 서버가 `/api` 와 `/ws` 를 FastAPI 로 프록시한다.

| 명령 | 하는 일 |
|---|---|
| `pnpm bootstrap` | `pnpm install` + `apps/api/.venv` 생성 및 의존성 설치 |
| `pnpm dev` | 백엔드 + 프론트 동시 실행. 로그에 `[api]` / `[web]` 접두어가 붙는다 |
| `pnpm dev:api` / `pnpm dev:web` | 한쪽만 (터미널을 따로 쓰고 싶을 때) |
| `pnpm test` | pytest + `tsc --noEmit` |

포트가 겹치면 `API_PORT` / `WEB_PORT` 로 바꾼다 (`WEB_PORT=5200 pnpm dev`).
`python` 을 못 찾는다고 하면 `PYTHON=C:/Python312/python.exe pnpm bootstrap` 처럼 경로를 직접 준다.

`make` 가 있으면 `make setup` / `make dev` 도 같은 일을 한다.

> **venv 가 깨진 것 같으면** — `apps/api/.venv` 에 `Scripts/`(또는 `bin/`)는 있는데 `python.exe` 가
> 없는 껍데기 상태가 되면 백엔드가 뜨지 않는다(도커에서 만든 venv 가 바인드 마운트로 새어
> 들어오거나 생성이 중간에 끊긴 경우). `pnpm setup:api` 가 이 상태를 감지해 지우고 다시 만든다.

### Docker

```bash
make up          # 개발 스택 (핫 리로드)      -> http://localhost:5173
make prod-up     # 운영 스택 (nginx 단일 진입점) -> http://localhost:8080
make down / make prod-down
```

#### Windows + WSL 조합 메모

| 상황 | 방법 |
|---|---|
| Docker Desktop (WSL2 백엔드) | `docker` 가 Windows PATH 에도 잡히므로 위 명령 그대로 |
| Docker Engine 을 WSL 안에만 설치 | WSL 셸에서 `make up` 하거나, Windows 에서 `make up COMPOSE="wsl docker compose"` |
| Windows 에 make 설치 | `winget install ezwinports.make` (Makefile 이 Git Bash 를 셸로 잡는다) |

Docker Desktop 없이 WSL 에만 엔진을 설치하려면 (sudo 비밀번호 없이 됨 — WSL 의 root 접근은 Windows 권한으로 통제된다):

```powershell
wsl -u root -e bash -lc "apt-get update && apt-get install -y docker.io docker-compose-v2 make"
wsl -u root -e bash -lc "usermod -aG docker $(wsl -e whoami)"
wsl -u root -e bash -lc "systemctl enable --now docker"
wsl --shutdown          # 그룹 반영
```

**⚠ WSL 은 세션이 모두 끝나면 VM 을 내려버린다.** 그러면 컨테이너도 같이 죽는다(`docker compose ps` 를 볼 때마다 "Up 4 seconds" 로 보이면 이 증상이다). 둘 중 하나로 해결한다.

- Ubuntu 터미널 창을 하나 열어둔 채 작업하거나
- `%USERPROFILE%\.wslconfig` 에 아래를 넣는다:

```ini
[wsl2]
vmIdleTimeout=-1
```

레포가 `C:\...` 에 있고 도커가 WSL 에서 돌면 마운트가 `/mnt/c` 를 거쳐 **느리고 파일 변경 감지가 안 된다.** 이때만 `.env` 에 `WATCH_POLLING=true` 를 넣으면 폴링으로 동작한다. 아예 빠르게 하려면 레포를 WSL 파일시스템(`~/projects/...`)에 두고 거기서 `make up` 하는 것이 정석이다.

> 일상 개발은 도커 없이 `make dev` 가 가장 빠르다. 도커는 운영 스택 검증(`make prod-up`)에 쓰는 것을 권한다.

### 검증

```bash
make test        # pytest + tsc --noEmit
make build       # 프론트 프로덕션 번들
```

pnpm 만 쓴다면 `pnpm test` / `pnpm build` 가 같은 일을 한다.

`make help` 로 전체 타깃 목록을 볼 수 있다. 모든 타깃은 루트 `package.json` 스크립트로도 미러링돼 있다(`pnpm test:api`, `pnpm up` 등).

---

## 구조

```
.
├─ Makefile                  개발/운영 엔트리포인트
├─ pnpm-workspace.yaml       apps/*, packages/*
├─ docker-compose.yml        개발 스택 (소스 마운트 + 리로드)
├─ docker-compose.prod.yml   운영 스택 (nginx + uvicorn)
├─ render.yaml               Render 배포 정의 (api=Docker, web=정적)
├─ .corepack.env             corepack auto-pin 차단 (런타임까지 적용)
├─ scripts/                  dev.mjs(api+web 동시 실행) · dev-env.mjs(경로·python 탐색)
│                            setup-api.mjs(venv 생성/복구) · run-pytest.mjs
│                            render-build.sh(pnpm 준비 → web 번들)
│                            render-postinstall.mjs(기본 `yarn` 빌드 커맨드 우회)
│                            serve-static.mjs(의존성 0 정적 서버)
│                            strip-package-manager.mjs(packageManager 필드 제거)
├─ apps/
│  ├─ api/                   FastAPI
│  │  ├─ app/
│  │  │  ├─ main.py          앱 + 60Hz 게임 루프 태스크
│  │  │  ├─ config.py        환경변수 설정
│  │  │  ├─ api/             routes.py(REST), ws.py(/ws/{code})
│  │  │  ├─ game/            constants·models·cards·physics·bullets·bots
│  │  │  │                   engine·sim(1틱 시뮬레이션)·stats(대미지 감쇠)
│  │  │  │                   serialize(스냅샷)·rooms(방 매니저)
│  │  │  ├─ schemas/         클라이언트 메시지 검증(pydantic)
│  │  │  ├─ services/        chat(메시지 생성), hub(WS 브로드캐스트)
│  │  │  └─ db/              (비어 있음) 영속화가 필요해지면 여기에
│  │  ├─ tests/              pytest
│  │  └─ Dockerfile          dev / runtime 멀티스테이지
│  └─ web/                   React + Vite
│     ├─ src/
│     │  ├─ types/game.ts    프로토콜 타입 (docs/PROTOCOL.md 와 1:1)
│     │  ├─ net/             WebSocket 싱글턴
│     │  ├─ store/           zustand — UI 상태만
│     │  ├─ game/            renderer·avatars·useInput
│     │  ├─ components/      GameCanvas·Hud·InfoPanel·KeyLegend·CardPicker·ChatBox 등
│     │  ├─ screens/         Lobby·Room·Game
│     │  └─ hooks/           useLocalProfile
│     ├─ Dockerfile          deps → dev / build → nginx runtime
│     └─ nginx.conf          SPA + /api·/ws 리버스 프록시
└─ docs/
   ├─ PROTOCOL.md            ★ 서버·클라이언트 단일 기준
   └─ DEPLOYMENT.md          배포 로드맵 (측정값 기반)
```

**[docs/PROTOCOL.md](docs/PROTOCOL.md) 가 서버와 클라이언트 사이의 계약이다.** 메시지 키를 바꾸려면 그 문서를 먼저 고친다.

---

## 조작

| 동작 | 키 |
|---|---|
| 이동 | `A` / `D` (또는 ← →) |
| 점프 | `W` · `Space` · `↑` |
| 조준 | 마우스 |
| 사격 | 좌클릭 |
| 강공격 | 좌클릭 350ms 이상 홀드 · `E` |
| 가드 | 우클릭 홀드 · `Shift` · `S` |
| 채팅 | `Enter` (해제 `Esc`) |
| 정보 보기 | `Tab` 홀드 — 거리별 대미지 / 내 스탯 / 보유 카드 |

---

## 설계 메모

- **60Hz 스냅샷은 React state 에 들어가지 않는다.** `net.latest` 에 mutable 로 쌓고 캔버스가 `requestAnimationFrame` 에서 직접 읽는다. HUD 등 UI 요소만 10Hz 이하로 샘플링한다.
- **서버가 모든 판정을 한다.** 클라이언트는 입력만 보낸다. 사격 쿨다운, 카드 선택 권한, 낙사, 대미지 계산 전부 서버 검증.
- **거리별 대미지 감쇠**: 발사 지점에서 0px 1.5배 → 600px 이상 0.4배(선형). 기본 탄 기준 근접 30 / 원거리 8. 공격력 배율은 발사 시점에 한 번만 적용한다.
- **대역폭**: 클라이언트 1명당 약 86 KB/s. 카드를 먹을 때만 바뀌는 필드(`stats`, `damage_table`)는 0.5초에 한 번만 싣는다. 더 줄이는 방법은 [DEPLOYMENT.md](docs/DEPLOYMENT.md) 3장.
- **API 프로세스는 1개만 띄운다.** 방 상태가 프로세스 메모리에 있어서 워커/레플리카를 늘리면 같은 방 플레이어가 갈라진다. 가로 확장 방법은 [DEPLOYMENT.md](docs/DEPLOYMENT.md) Phase 3.
- **파일 하나당 400줄 이내.** 넘으면 모듈을 쪼갠다.

## DB

현재 **DB 없이 전부 인메모리**로 동작한다(서버를 재시작하면 방과 매치가 사라진다). 코인/외형은 브라우저 `localStorage` 에 있어 위조 가능하다.

계정, 서버 권위 코인/레벨, 스킨 소유권, 전적 랭킹 중 하나라도 필요해지면 `apps/api/app/db/` 에 Postgres + SQLAlchemy + Alembic 을 붙인다. 자세한 조건과 주의점은 [DEPLOYMENT.md](docs/DEPLOYMENT.md) Phase 4.

## 아직 없는 것

기획서([docs/PvP_로그라이크_슈팅게임_개발문서.md](docs/PvP_로그라이크_슈팅게임_개발문서.md)) 대비 미구현:

- 랜덤 맵 시스템 (현재 고정 맵 1종). 얼음/붕괴/회전/용암맵, 움직이는 발판
- 벽 점프 / 벽 슬라이드
- 빠른 대전 매치메이킹 (현재는 방 코드 방식만)
- 빌드 추천 표시, 시너지 이름 출력
- 관전 모드, 레벨/경험치 보상, 스킨 상점 서버 연동
