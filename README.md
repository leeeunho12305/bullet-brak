# Bullet Brak

ROUNDS 스타일 2D PvP 물리 슈팅 게임. **FastAPI(서버 권위 60Hz 시뮬레이션) + React 19(Vite + TypeScript)**.

- 라운드 2승 = 1점, 먼저 5점을 내면 매치 승리
- 라운드에서 진 쪽이 카드 5장 중 1장을 골라 빌드를 쌓는다 (카드 67종)
- 물리 기반 전투: 넉백, 낙사, 도탄, 폭발, 가드 반사, 자기 탄에 자기가 맞음

---

## 실행

### 1. 백엔드 (FastAPI)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.sample .env              # 필요하면 값 수정
uvicorn app.main:app --reload --port 8000
```

### 2. 프론트엔드 (React)

```bash
cd frontend
npm install
cp .env.sample .env              # 기본값(동일 오리진 프록시)이면 없어도 됨
npm run dev                      # http://localhost:5173
```

Vite dev 서버가 `/api` 와 `/ws` 를 `127.0.0.1:8000` 으로 프록시하므로, 브라우저는 5173 하나만 보면 된다.

### 테스트

```bash
cd backend && pytest tests -q        # 게임 규칙 / 스냅샷 / 대미지 감쇠
cd frontend && npm run typecheck     # tsc --noEmit
```

---

## 구조

```
backend/app/
  main.py            FastAPI 앱 + 60Hz 게임 루프 태스크
  config.py          환경변수 설정 (.env)
  api/               routes.py(REST), ws.py(/ws/{code})
  game/
    constants.py     월드/밸런스 상수
    models.py        Player, Bot, Bullet, Zone, Room
    cards.py         카드 67종과 효과
    physics.py       충돌, 폭발, 치명타 처리
    bullets.py       탄환 생성/시뮬레이션(유도·도탄·폭발·관통·가드반사)
    bots.py          훈련장 봇 AI
    engine.py        1틱 시뮬레이션 + 라운드/매치 판정
    sim.py           플레이어 물리, 가드 효과, 장판
    stats.py         거리별 대미지 감쇠, HUD 스탯 요약
    serialize.py     스냅샷 직렬화
    rooms.py         방 매니저
  schemas/messages.py  클라이언트 메시지 검증(pydantic)
  services/          chat.py(욕설 필터), hub.py(WS 브로드캐스트)
  db/                (비어 있음) 영속화가 필요해지면 여기에

frontend/src/
  types/game.ts      프로토콜 타입 (docs/PROTOCOL.md 와 1:1)
  net/connection.ts  WebSocket 싱글턴
  store/gameStore.ts zustand — UI 상태만
  game/              renderer.ts, avatars.ts, avatarParts.ts, useInput.ts
  components/        GameCanvas, Hud, InfoPanel, KeyLegend, CardPicker, ChatBox, AvatarEditor, GameOverOverlay
  screens/           LobbyScreen, RoomScreen, GameScreen
  hooks/             useLocalProfile (닉네임/외형/코인 localStorage)
```

**[docs/PROTOCOL.md](docs/PROTOCOL.md) 가 서버와 클라이언트 사이의 단일 기준이다.** 메시지 키를 바꾸려면 그 문서를 먼저 고친다.

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
- **파일 하나당 400줄 이내.** 넘으면 모듈을 쪼갠다.

## DB

현재 **DB 없이 전부 인메모리**로 동작한다(서버를 재시작하면 방과 매치가 사라진다). 코인/외형은 브라우저 `localStorage` 에 있어 위조 가능하다.

아래가 필요해지면 `backend/app/db/` 에 SQLAlchemy + Alembic 을 붙인다.

- 계정 / 닉네임 영속화
- 코인, 레벨, 경험치 (서버 권위로 이전)
- 스킨 / 아이템 소유권
- 전적, 랭킹, 매치 히스토리

## 아직 없는 것

기획서([docs/PvP_로그라이크_슈팅게임_개발문서.md](docs/PvP_로그라이크_슈팅게임_개발문서.md)) 대비 미구현:

- 랜덤 맵 시스템 (현재 고정 맵 1종). 얼음/붕괴/회전/용암맵, 움직이는 발판
- 벽 점프 / 벽 슬라이드
- 빠른 대전 매치메이킹 (현재는 방 코드 방식만)
- 빌드 추천 표시, 시너지 이름 출력
- 관전 모드, 레벨/경험치 보상, 스킨 상점 서버 연동
