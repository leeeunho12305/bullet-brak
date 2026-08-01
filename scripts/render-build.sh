#!/usr/bin/env sh
# Render 빌드 — pnpm 활성화 → 의존성 설치 → 정적 번들(apps/web/dist) 생성.
#
# 두 경로로 들어온다.
#   1) render.yaml 의 buildCommand          (Blueprint 로 만든 서비스 — 권장)
#   2) scripts/render-postinstall.mjs 경유  (대시보드로 만든 서비스. Build Command 가
#      기본값 `yarn` 이라 yarn install 의 postinstall 훅을 타고 들어온다)
#
# 로컬 확인: sh scripts/render-build.sh
set -eu

cd "$(dirname "$0")/.."

# pnpm 버전 고정 지점은 여기, apps/web/Dockerfile, .github/workflows/ci.yml 세 곳이다.
# (루트 package.json 의 packageManager 필드는 못 쓴다 — package.json 의 주석 참고)
PNPM_VERSION="9.15.4"

# Render 빌드 환경인가. postinstall 경유로 들어온 경우에도 동일하게 잡힌다.
ON_RENDER="${RENDER:-}${RENDER_SERVICE_ID:-}"

# 아래 pnpm install 이 루트 postinstall 을 다시 부르므로 재귀를 막는다.
BULLET_BRAK_RENDER_BUILD=1
export BULLET_BRAK_RENDER_BUILD

# 최신 Node 배포판은 corepack 이 빠져 있을 수 있어서 npm 전역 설치를 대비책으로 둔다.
if corepack enable >/dev/null 2>&1 && corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null 2>&1; then
  echo "==> corepack 으로 pnpm ${PNPM_VERSION} 활성화"
else
  echo "==> corepack 사용 불가, npm 으로 pnpm ${PNPM_VERSION} 설치"
  npm install -g --force "pnpm@${PNPM_VERSION}"
fi

echo "==> pnpm $(pnpm --version) / node $(node --version)"

if [ -n "$ON_RENDER" ]; then
  # yarn 이 먼저 만들어 둔 node_modules 가 남아 있으면 pnpm 이 "다른 패키지 매니저가 만든
  # 디렉터리"라며 지우고 다시 깔지 되묻는다(비대화형에서 애매하게 넘어간다). 먼저 치운다.
  rm -rf node_modules apps/web/node_modules
fi

pnpm install --frozen-lockfile
pnpm --filter @bullet-brak/web build

DIST="apps/web/dist"
echo "==> 빌드 완료: ${DIST}"

if [ -n "$ON_RENDER" ]; then
  # 대시보드의 Publish Directory 값이 뭔지는 저장소에서 알 수 없다.
  # 흔히 쓰는 경로에 같은 산출물을 복사해서 어느 쪽으로 잡혀 있어도 서비스가 뜨게 한다.
  # (Render 의 임시 체크아웃에만 생기는 사본이라 저장소는 더러워지지 않는다)
  for MIRROR in dist build apps/web/build; do
    rm -rf "$MIRROR"
    mkdir -p "$MIRROR"
    cp -R "$DIST"/. "$MIRROR"/
    echo "==> 사본: ${MIRROR}"
  done
  echo "==> Publish Directory 는 apps/web/dist 권장 (dist, build, apps/web/build 도 동일 내용)"
fi
