# 빌드 컨텍스트는 저장소 루트다 (pnpm 워크스페이스 lockfile 이 루트에 있음).
#   docker build -f apps/web/Dockerfile --target runtime .
#
# 이 이미지는 배포 전용이다. 로컬 개발은 도커 없이 `make dev` 로 한다.

# ── 의존성 설치 ──────────────────────────────────────────────
FROM node:22-alpine AS deps
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
# 루트 package.json 에 packageManager 필드가 없으므로(이유는 그 파일 주석 참고)
# 버전을 여기서 직접 고정한다. scripts/render-build.sh·CI 와 같은 값이어야 한다.
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc .corepack.env ./
COPY apps/web/package.json apps/web/
# 루트 package.json 의 postinstall 훅이 이 파일을 부른다. 없으면 install 이 MODULE_NOT_FOUND 로 죽는다.
# (Render 밖에서는 즉시 exit 0 이라 실제로 하는 일은 없다 — scripts/render-postinstall.mjs 주석 참고)
COPY scripts/render-postinstall.mjs scripts/
RUN pnpm install --frozen-lockfile

# ── 정적 번들 빌드 ───────────────────────────────────────────
FROM deps AS build
COPY apps/web apps/web
RUN pnpm --filter @bullet-brak/web build

# ── 운영: nginx 가 정적 파일 서빙 + API/WS 리버스 프록시 ──────
FROM nginx:1.27-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
