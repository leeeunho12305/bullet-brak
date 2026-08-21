# Bullet Brak

ROUNDS 스타일 2D PvP 물리 슈팅 게임. **FastAPI(서버 권위 60Hz 시뮬레이션) + React 19(Vite + TypeScript)** 모노레포.

- 라운드 2승 = 1점, 먼저 5점을 내면 매치 승리
- 라운드에서 진 쪽이 카드 5장 중 1장을 골라 빌드를 쌓는다 (카드 66종). 훈련장에서는 카드가 전부 열려 있어 아무 때나 원하는 것을 시험해 볼 수 있다
- 물리 기반 전투: 넉백, 낙사, 도탄, 폭발, 가드 반사, 거리별 대미지 감쇠

---

## 빠른 시작

```bash
make setup     # 백엔드 venv + 프론트 pnpm 의존성
make dev       # api(:8000) + web(:5173) 동시 실행
```

`make` 가 없으면 (Windows 기본 환경 등):

```bash
# 1) 백엔드
cd apps/api
python -m venv .venv
.venv/Scripts/activate                    # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# 2) 프론트 (다른 터미널)
corepack enable pnpm                      # pnpm 이 없다면 (관리자 권한 필요할 수 있음)
pnpm install
pnpm dev                                  # http://localhost:5173
```

브라우저는 **http://localhost:5173** 하나만 보면 된다. vite dev 서버가 `/api` 와 `/ws` 를 FastAPI 로 프록시한다.

### Docker (배포 전용)

**도커는 배포에만 쓴다.** 개발용 compose 스택과 Dockerfile 의 dev 스테이지는 없다 —
로컬 개발 경로는 위의 `make dev` 하나뿐이다.

```bash
make up      # 배포 스택 (api + postgres + nginx) -> http://localhost:8080
make down
```

`docker-compose.yml` 이 곧 배포 단위다(Dokploy/Coolify 가 이 파일을 그대로 읽는다).
**`POSTGRES_PASSWORD` 가 없으면 기동을 거부한다** — `.env` 에 넣거나 환경변수로 준다.

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

> 배포 스택은 소스를 마운트하지 않고 이미지에 굽기 때문에, 예전의 `/mnt/c` 마운트 성능·파일감지 문제는
> 더 이상 없다. 일상 개발은 `make dev`, 도커는 배포(와 배포 전 검증)에만 쓴다.

### 검증

```bash
make test        # pytest + tsc --noEmit
make build       # 프론트 프로덕션 번들
```

`make help` 로 전체 타깃 목록을 볼 수 있다. 모든 타깃은 루트 `package.json` 스크립트로도 미러링돼 있다(`pnpm test:api`, `pnpm up` 등).

---

## 구조

```
.
├─ Makefile                  개발/배포 엔트리포인트
├─ pnpm-workspace.yaml       apps/*, packages/*
├─ docker-compose.yml        배포 스택 (nginx + uvicorn + postgres) — 도커는 이것뿐이다
├─ render.yaml               Render 배포 정의 (api=Docker, web=정적)
├─ .corepack.env             corepack auto-pin 차단 (런타임까지 적용)
├─ scripts/                  render-build.sh(pnpm 준비 → web 번들)
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
│  │  │  │                   maps(맵 카탈로그)·blocks(점프대·이동발판·빙판·가시)
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
│     │  ├─ components/      GameCanvas·Hud·InfoPanel·CardPicker·ChatBox
│     │  │                   ControlsGuide(조작법)·Tutorial·MapPicker·MapEditor 등
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

조작법 전체는 로비 "플레이어" 패널 아래(캐릭터 꾸미기 밑)에 있다. 처음이라면 로비의 **📖 튜토리얼**을 먼저 보면 된다.

## 맵과 블럭

발판은 종류를 갖는다(`app/game/blocks.py`). 대기실에서 방장이 **🧱 맵 에디터**로 직접 배치할 수도 있다.

| 블럭 | 효과 |
|---|---|
| 일반 블럭 | 위/아래/옆 전부 막힌다 |
| 점프대 | 밟으면 높이 튀어오르고 공중 점프가 다시 찬다 |
| 이동 발판 | 정해진 구간을 왕복하고, 올라탄 사람을 같이 나른다 |
| 빙판 | 마찰이 거의 없다 |
| 가시 | 닿아 있는 동안 피해를 입고 튕겨난다 |

---

## 설계 메모

- **60Hz 스냅샷은 React state 에 들어가지 않는다.** `net.latest` 에 mutable 로 쌓고 캔버스가 `requestAnimationFrame` 에서 직접 읽는다. HUD 등 UI 요소만 10Hz 이하로 샘플링한다.
- **서버가 모든 판정을 한다.** 클라이언트는 입력만 보낸다. 사격 쿨다운, 카드 선택 권한, 낙사, 대미지 계산 전부 서버 검증.
- **거리별 대미지 감쇠**: 발사 지점에서 0px 1.5배 → 600px 이상 0.4배(선형). 기본 탄 기준 근접 30 / 원거리 8. 공격력 배율은 발사 시점에 한 번만 적용한다.
- **대역폭**: 클라이언트 1명당 약 86 KB/s. 카드를 먹을 때만 바뀌는 필드(`stats`, `damage_table`)는 0.5초에 한 번만 싣는다. 더 줄이는 방법은 [DEPLOYMENT.md](docs/DEPLOYMENT.md) 3장.
- **API 프로세스는 1개만 띄운다.** 방 상태가 프로세스 메모리에 있어서 워커/레플리카를 늘리면 같은 방 플레이어가 갈라진다. 가로 확장 방법은 [DEPLOYMENT.md](docs/DEPLOYMENT.md) Phase 3.
- **파일 하나당 400줄 이내.** 넘으면 모듈을 쪼갠다.

## DB

**Postgres 는 선택 사항이다.** `DATABASE_URL` 이 비어 있으면 서버는 예전처럼 순수 인메모리로 뜨고,
계정·코인 영속화만 꺼진다. 게임 자체는 어느 쪽이든 똑같이 동작한다.

| | `DATABASE_URL` 없음 | 있음 |
|---|---|---|
| 방/매치 상태 | 메모리 (재시작하면 소멸) | 메모리 (동일 — DB 에 넣지 않는다) |
| 닉네임·아바타 | localStorage | 계정에 저장, 기기 간 동기화 |
| 코인 | localStorage = **위조 가능** | 서버 권위 |
| 로그인 (다른 기기) | 없음 | 아이디/비밀번호 · 인계 코드 |
| `/api/auth/*`, `/api/me` | 503 | 정상 |

- **신원**: 회원가입 화면이 없다. 앱을 열면 익명 계정이 자동 생성되고, 브라우저가 디바이스 토큰
  (`localStorage.bulletBrakToken`)을 들고 있고 서버는 그 sha256 해시로 계정을 찾는다.
  WS `join` 에 토큰을 실으면 그 판의 코인이 계정 잔액으로 확정된다. 계약은 [PROTOCOL.md](docs/PROTOCOL.md) §1.1.
- **로그인**: 로비에서 아이디/비밀번호를 정하면 **쓰던 익명 계정이 그대로 승격된다**(코인이 따라온다).
  다른 기기에서 그 아이디로 들어오면 같은 계정이 열린다. 비밀번호를 잊었을 때를 위해
  **인계 코드**(`K7M2-9QPX-3W5B`)를 발급받아 둘 수 있다 — 이메일이 없는 구조라 복구 경로가 하나는 필요하다.
  코드 평문은 발급 응답에서 한 번만 나오고, 재발급하면 옛 코드는 죽는다.
- **비밀번호 해싱은 워커 스레드에서 돈다.** bcrypt 한 번이 60~100ms 인데 이 프로세스의
  이벤트 루프는 60Hz 틱 루프와 같은 루프다 — 동기로 부르면 틱이 밀린다
  (`app/services/passwords.py`, 가드는 `tests/test_passwords.py`).
- **스키마**: `apps/api/app/db/` — SQLAlchemy 2.0(async) + Alembic. 마이그레이션은
  **서버가 기동할 때 스스로 `upgrade head`** 를 돌린다(compose/Render 어디서든 동작이 같다).
- **게임 루프는 DB 를 건드리지 않는다.** 60Hz 틱에 `await db` 가 끼면 틱이 밀린다.
  DB 접근은 입장(join)·REST·매치 종료 같은 저빈도 지점뿐이다.
- **구매도 서버 권위다.** 파츠 가격표는 `apps/api/app/game/shop_prices.json` 에 있고,
  이 파일은 프런트 카탈로그에서 생성된다(`pnpm shop:prices`). 클라이언트는 아이템 키만 보내고
  가격은 서버가 정한다.

`make dev`(로컬)에는 Postgres 가 없어서 인메모리 모드로 돈다. DB 가 붙은 구성은
`docker-compose.yml`(= 배포 스택) 하나뿐이다.

### 파츠 가격표를 서버가 아는 방법

가격의 단일 진실은 여전히 프런트(`apps/web/src/game/avatarParts.ts`)다. 등급(`tier`)만 적으면
파일 하단의 **안정 정렬**이 인덱스를 확정하고, 눈 파츠는 눈모양 × 눈썹 조합으로 생성된다 —
즉 인덱스↔가격 매핑을 사람이 옮겨 적으면 반드시 어긋난다.

그래서 서버용 표는 **생성물**이다:

```bash
pnpm shop:prices    # avatarParts.ts 를 평가해 apps/api/app/game/shop_prices.json 재생성
```

**파츠를 추가/삭제하거나 등급을 바꿨으면 반드시 다시 돌리고 결과를 커밋한다.**
안 돌리면 서버가 옛 가격으로 판정한다.

## 아직 없는 것

기획서([docs/PvP_로그라이크_슈팅게임_개발문서.md](docs/PvP_로그라이크_슈팅게임_개발문서.md)) 대비 미구현:

- 붕괴/회전 발판 (점프대·이동발판·빙판·가시는 구현됨 — `app/game/blocks.py`)
- 벽 점프 / 벽 슬라이드
- 빠른 대전 매치메이킹 (현재는 방 코드 방식만)
- 빌드 추천 표시, 시너지 이름 출력
- 관전 모드, 레벨/경험치 보상, 스킨 상점 서버 연동
