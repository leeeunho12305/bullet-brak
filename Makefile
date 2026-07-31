# Bullet Brak — 개발/운영 엔트리포인트
# 사용법: make <target>  (그냥 `make` 만 치면 목록이 나온다)
#
# 설치:
#   Windows : winget install ezwinports.make   (Git for Windows 가 이미 있어야 한다)
#   WSL/Linux/macOS : 대부분 기본 설치됨
# make 없이 쓰려면 루트 package.json 의 pnpm 스크립트가 같은 일을 한다.

API_DIR  := apps/api
WEB_DIR  := apps/web
PNPM     ?= pnpm
COMPOSE  ?= docker compose
PROD     := $(COMPOSE) -f docker-compose.prod.yml

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
else
SHELL := /bin/sh
VENV_BIN := $(API_DIR)/.venv/bin
PY       ?= python3
endif
VENV_PY  := $(VENV_BIN)/python

# docker 를 WSL 안에만 설치했고 make 는 Windows 에서 돌리는 경우:
#   make up COMPOSE="wsl docker compose"
# (WSL 이 현재 디렉터리를 /mnt/c/... 로 자동 변환해준다. 다만 느리다 — README 참고)

.DEFAULT_GOAL := help
.PHONY: help setup setup-api setup-web dev dev-api dev-web test test-api typecheck build \
        up down restart logs ps images prod-up prod-down clean

help: ## 사용 가능한 타깃 목록
	@echo "Bullet Brak"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

## ── 로컬 개발 (컨테이너 없이) ─────────────────────────────────

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

## ── docker compose ──────────────────────────────────────────

up: ## 개발 스택 기동 (http://localhost:5173)
	$(COMPOSE) up -d --build
	@echo "web  -> http://localhost:5173"
	@echo "api  -> http://localhost:8000/api/health"

down: ## 개발 스택 종료
	$(COMPOSE) down

restart: down up ## 개발 스택 재기동

logs: ## 로그 따라가기 (make logs s=api 로 서비스 지정 가능)
	$(COMPOSE) logs -f $(s)

ps: ## 컨테이너 상태
	$(COMPOSE) ps

images: ## 운영 이미지 빌드만 수행
	$(PROD) build

prod-up: ## 운영 스택 기동 (nginx 단일 진입점, http://localhost:8080)
	$(PROD) up -d --build
	@echo "web  -> http://localhost:8080"

prod-down: ## 운영 스택 종료
	$(PROD) down

## ── 정리 ────────────────────────────────────────────────────

clean: ## 빌드 산출물/캐시 삭제 (의존성은 남긴다)
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/*.tsbuildinfo
	find $(API_DIR) -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf $(API_DIR)/.pytest_cache
