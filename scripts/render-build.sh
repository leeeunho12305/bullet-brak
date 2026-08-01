#!/usr/bin/env sh
# Render 정적 사이트(apps/web) 빌드 스크립트.
#
# ⚠ Render 의 Node 기본 Build Command 는 `yarn` 이다. 이 저장소는 pnpm 워크스페이스라
#   yarn 1 이 package.json 의 "packageManager": "pnpm@..." 을 보고 아래처럼 죽는다.
#     error This project's package.json defines "packageManager": "yarn@pnpm@9.15.4"
#   그래서 서비스의 Build Command 를 `./scripts/render-build.sh` 로 바꿔야 한다.
#
# 로컬에서도 같은 결과를 확인할 수 있다: sh scripts/render-build.sh
set -eu

cd "$(dirname "$0")/.."

# 버전은 package.json 의 packageManager 필드 하나만 보고 따라간다(중복 정의 금지).
PNPM_VERSION="$(node -p "require('./package.json').packageManager.split('@')[1]")"

# 최신 Node 배포판은 corepack 이 빠져 있을 수 있어서 npm 전역 설치를 대비책으로 둔다.
if corepack enable >/dev/null 2>&1 && corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null 2>&1; then
  echo "==> corepack 으로 pnpm ${PNPM_VERSION} 활성화"
else
  echo "==> corepack 사용 불가, npm 으로 pnpm ${PNPM_VERSION} 설치"
  npm install -g --force "pnpm@${PNPM_VERSION}"
fi

echo "==> pnpm $(pnpm --version) / node $(node --version)"

pnpm install --frozen-lockfile
pnpm --filter @bullet-brak/web build
