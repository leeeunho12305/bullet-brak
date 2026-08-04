#!/usr/bin/env sh
# Render 빌드 — pnpm 준비 → 의존성 설치 → 정적 번들(apps/web/dist) 생성.
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

# corepack 방어선. 직접 부르지는 않지만 PATH 에 shim 이 깔려 있을 수 있다.
#   AUTO_PIN=0 : spec 이 없을 때 package.json 에 packageManager 를 써 넣지 못하게 막는다.
#                (이게 켜져 있어서 런타임 `yarn start` 가 "configured to use pnpm" 으로 죽었다)
#   STRICT=0   : 프로젝트 spec 과 다른 매니저를 불러도 예외 대신 그냥 실행한다.
COREPACK_ENABLE_AUTO_PIN=0
COREPACK_ENABLE_STRICT=0
export COREPACK_ENABLE_AUTO_PIN COREPACK_ENABLE_STRICT

# pnpm 은 npm 전역 설치로 받는다. corepack shim 은 위 auto-pin 부작용이 있고,
# Windows 등 일부 환경에선 shim 설치 자체가 권한 문제로 실패한다.
echo "==> pnpm ${PNPM_VERSION} 설치 (npm 전역)"
npm install -g --force "pnpm@${PNPM_VERSION}"

# PATH 앞쪽에 corepack shim 이 있을 수 있으니 설치된 실제 바이너리를 직접 가리킨다.
PNPM="$(npm prefix -g)/bin/pnpm"
[ -x "$PNPM" ] || PNPM="pnpm"

echo "==> pnpm $("$PNPM" --version) / node $(node --version)"

if [ -n "$ON_RENDER" ]; then
  # yarn 이 먼저 만들어 둔 node_modules 가 남아 있으면 pnpm 이 "다른 패키지 매니저가 만든
  # 디렉터리"라며 지우고 다시 깔지 되묻는다(비대화형에서 애매하게 넘어간다). 먼저 치운다.
  rm -rf node_modules apps/web/node_modules
fi

"$PNPM" install --frozen-lockfile
"$PNPM" --filter @bullet-brak/web build

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

# 마지막 방어선: 빌드 도중 누가 packageManager 를 써 넣었다면 업로드 전에 지운다.
# 이게 남아 있으면 런타임 `yarn start` 가 corepack 에 막혀 죽는다.
node scripts/strip-package-manager.mjs

# 게임 서버(FastAPI)를 같은 서비스에서 같이 띄우기 위한 의존성 설치 — 되면 좋고 아니면 만다.
# Render 의 Node 런타임 이미지에 python3 가 있는지 보장되지 않으므로 실패해도 빌드는 계속한다.
# 실패하면 정적 사이트로만 뜨고, 프록시는 외부 API_ORIGIN 을 바라본다(지금과 동일).
#: 게임 서버 의존성을 심는 곳. serve-static.mjs 가 같은 경로를 PYTHONPATH 로 준다.
PYDEPS="$(pwd)/apps/api/.pydeps"

install_api_deps() {
  PY=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "==> python 없음. API 를 같이 띄울 수 없다(정적 사이트로만 동작)."
    return 0
  fi

  echo "==> $("$PY" --version 2>&1) 감지. API 의존성 설치 시도"
  if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "==> pip 없음. ensurepip 로 부트스트랩"
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi

  # --user 는 런타임에 HOME/파이썬 버전이 달라지면 못 찾는다(실제로 uvicorn 이
  # exited(1) 로 죽었다). 프로젝트 안에 --target 으로 박고 런타임에 PYTHONPATH 로 준다.
  if "$PY" -m pip install --target "$PYDEPS" --no-cache-dir -r apps/api/requirements.txt; then
    echo "==> API 의존성 설치 완료 -> ${PYDEPS}"
    "$PY" -c "import sys; sys.path.insert(0, '${PYDEPS}'); import uvicorn, fastapi; print('==> 검증 OK: uvicorn', uvicorn.__version__)" \
      || echo "==> 설치는 됐는데 import 가 안 된다. 런타임에서 폴백할 것이다."
  else
    echo "==> API 의존성 설치 실패. 정적 사이트로만 동작한다."
  fi
  return 0
}

install_api_deps || true
