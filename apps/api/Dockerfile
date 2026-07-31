# 빌드 컨텍스트: apps/api
#   docker build -f apps/api/Dockerfile apps/api

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── 개발: 소스는 볼륨으로 마운트, --reload ────────────────────
FROM base AS dev
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── 운영 ─────────────────────────────────────────────────────
FROM base AS runtime
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"
# ⚠ --workers 1 고정: 방/매치 상태가 프로세스 메모리에 있어 워커를 늘리면
#   같은 방의 플레이어가 서로 다른 워커에 붙어 게임이 갈라진다. docs/DEPLOYMENT.md 참고.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
