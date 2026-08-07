# Bullet Brak — 개발/배포 엔트리포인트
# 사용법: make <target>  (그냥 `make` 만 치면 목록이 나온다)
#
# ⚠ 도커는 배포 전용이다. 로컬 개발은 `make dev` (python venv + vite dev server) 하나뿐이다.
#   docker-compose.yml 은 배포 스택(api + db + nginx)이고, `make up` 은 그걸 띄운다.
#   개발용 compose 스택과 Dockerfile 의 dev 스테이지는 전부 제거했다.
#
# 설치:
#   Windows : winget install ezwinports.make   (Git for Windows 가 이미 있어야 한다)
#   WSL/Linux/macOS : 대부분 기본 설치됨
# make 없이 쓰려면 루트 package.json 의 pnpm 스크립트가 같은 일을 한다.

API_DIR  := apps/api
WEB_DIR  := apps/web
# pnpm 이 PATH 에 없으면 corepack 으로 대신 부른다(`corepack enable pnpm` 을 안 한 환경).
# package.json 에 packageManager 필드가 없어서 corepack 에 버전을 직접 준다.
PNPM     ?= $(shell command -v pnpm >/dev/null 2>&1 && echo pnpm || echo corepack pnpm@9.15.4)
# compose 파일은 docker-compose.yml 하나뿐이다(= 배포 스택).
COMPOSE  ?= docker compose

ifeq ($(OS),Windows_NT)
# Windows make 의 기본 셸은 cmd.exe 라서 grep/awk/rm/find 가 없다.
# Git for Windows 의 bash 를 셸로 쓴다(경로는 GIT_BASH 로 덮어쓸 수 있다).
GIT_BASH ?= C:/Program Files/Git/bin/bash.exe
ifneq ($(wildcard $(GIT_BASH)),)
SHELL := $(GIT_BASH)
.SHELLFLAGS := -o pipefail -c
endif
VENV_BIN := $(API_DIR)/.venv/Scripts
PY       ?= python
# Windows PATH 에서는 System32\find.exe 가 먼저 잡힌다(문법이 전혀 다르다). Git 쪽을 쓴다.
FIND     := /usr/bin/find
else
SHELL := /bin/sh
VENV_BIN := $(API_DIR)/.venv/bin
PY       ?= python3
FIND     := find
endif
VENV_PY  := $(VENV_BIN)/python

# docker 를 WSL 안에만 설치했고 make 는 Windows 에서 돌리는 경우:
#   make up COMPOSE="wsl docker compose"
# (WSL 이 현재 디렉터리를 /mnt/c/... 로 자동 변환해준다. 다만 느리다 — README 참고)

.DEFAULT_GOAL := help
.PHONY: help setup setup-api setup-web dev dev-api dev-web test test-api typecheck build \
        up down restart logs ps images clean \
        migrate migration migrate-down db-shell db-dump

help: ## 사용 가능한 타깃 목록
	@echo "Bullet Brak"
	@# Windows make 는 recipe 명령줄을 ANSI 로 변환해 넘긴다 — 여기 한글을 쓰면 깨진다. ASCII 로만 쓸 것.
	@echo "  local dev : make setup && make dev   (no docker)"
	@echo "  deploy    : make up                  (docker-compose.yml)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

## ── 로컬 개발 (도커 없음 — 유일한 개발 경로) ──────────────────
# 처음이라면: make setup  →  make dev

setup: setup-api setup-web ## 백엔드 venv + 프론트 의존성 한 번에 설치

setup-api: ## 백엔드 가상환경 생성 및 의존성 설치
	$(PY) -m venv $(API_DIR)/.venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r $(API_DIR)/requirements-dev.txt
	@echo "완료: $(API_DIR)/.env.sample 을 .env 로 복사하면 설정을 바꿀 수 있다."

setup-web: ## 프론트 의존성 설치 (pnpm 워크스페이스)
	$(PNPM) install

dev: ## 백엔드 + 프론트 동시 실행 (Ctrl+C 로 둘 다 종료)
	$(MAKE) -j2 dev-api dev-web

dev-api: ## FastAPI 개발 서버 (http://127.0.0.1:8000)
	cd $(API_DIR) && ../../$(VENV_BIN)/uvicorn app.main:app --reload --port 8000

dev-web: ## Vite 개발 서버 (http://localhost:5173)
	$(PNPM) --filter @bullet-brak/web dev

## ── 검증 ────────────────────────────────────────────────────

test: test-api typecheck ## 전체 검증 (pytest + tsc)

test-api: ## 백엔드 테스트
	cd $(API_DIR) && ../../$(VENV_PY) -m pytest tests -q

typecheck: ## 프론트 타입 검사
	$(PNPM) -r typecheck

build: ## 프론트 프로덕션 번들 생성
	$(PNPM) --filter @bullet-brak/web build

## ── docker compose (배포 스택 전용) ──────────────────────────
# 도커는 배포에만 쓴다. 아래 타깃은 전부 docker-compose.yml = 배포 스택을 가리킨다.
# POSTGRES_PASSWORD 가 없으면 compose 가 기동을 거부한다(.env 또는 환경변수로 넣을 것).

up: ## 배포 스택 기동 (api+db+nginx, 단일 진입점 :8080)
	$(COMPOSE) up -d --build
	@echo "web  -> http://localhost:$${WEB_PROD_PORT:-8080}"
	@echo "api  -> http://localhost:$${WEB_PROD_PORT:-8080}/api/health  (nginx 프록시 경유)"

down: ## 배포 스택 종료
	$(COMPOSE) down

restart: down up ## 배포 스택 재기동

logs: ## 배포 스택 로그 따라가기 (make logs s=api 로 서비스 지정 가능)
	$(COMPOSE) logs -f $(s)

ps: ## 배포 스택 컨테이너 상태
	$(COMPOSE) ps

images: ## 배포 이미지 빌드만 수행
	$(COMPOSE) build

## ── DB ──────────────────────────────────────────────────────
# Postgres 는 배포 스택(docker-compose.yml)에만 있다. `make dev` 는 DB 없이 인메모리로 돈다.
# 평소엔 아래를 칠 일이 없다 — api 가 기동할 때 alembic upgrade head 를 스스로 돌린다.
# 리비전을 새로 만들거나 데이터를 직접 들여다볼 때만 쓴다(스택이 떠 있어야 한다).

migrate: ## 마이그레이션 적용 (배포 스택 컨테이너 안에서 alembic upgrade head)
	$(COMPOSE) exec api alembic upgrade head

migration: ## 모델 변경으로 리비전 생성 (make migration m="설명")
	@test -n "$(m)" || { echo 'm= 로 설명을 넘길 것. 예: make migration m="add ranking"'; exit 1; }
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"
	@echo "생성된 파일을 반드시 눈으로 확인할 것 — autogenerate 는 완벽하지 않다."

migrate-down: ## 마이그레이션 한 단계 되돌리기
	$(COMPOSE) exec api alembic downgrade -1

db-shell: ## psql 접속
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-bulletbrak} -d $${POSTGRES_DB:-bulletbrak}

db-dump: ## DB 덤프를 stdout 으로 (make db-dump > backup.sql)
	@$(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-bulletbrak} -d $${POSTGRES_DB:-bulletbrak}

## ── 정리 ────────────────────────────────────────────────────

clean: ## 빌드 산출물/캐시 삭제 (의존성은 남긴다)
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/*.tsbuildinfo
	$(FIND) $(API_DIR) -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf $(API_DIR)/.pytest_cache
