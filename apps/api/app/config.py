"""환경변수 기반 설정. `.env.sample` 참고."""

from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

#: asyncpg 가 모르는 libpq 전용 쿼리 파라미터. URL 에 붙어 있으면 연결 자체가 실패한다.
#: (Render/Neon/Supabase 가 주는 문자열에 sslmode 가 섞여 오는 게 대표적)
_LIBPQ_ONLY_PARAMS = {
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "channel_binding",
    "gssencmode",
    "target_session_attrs",
    "connect_timeout",
    "application_name",
    "options",
}

#: sslmode 값 -> asyncpg 의 ssl 인자. disable/allow 는 SSL 을 강제하지 않는다.
_SSLMODE_TO_ASYNCPG = {
    "require": "require",
    "verify-ca": "verify-ca",
    "verify-full": "verify-full",
    "prefer": "prefer",
}


def normalize_database_url(raw: str) -> tuple[str, dict[str, Any]]:
    """배포처가 주는 DB URL 을 SQLAlchemy(asyncpg) 가 먹을 수 있는 형태로 정규화한다.

    맞춰야 하는 것이 두 가지다.

    1. **드라이버 지정** — Render 의 `fromDatabase` 나 Dokploy/Coolify 의 서비스 링크는
       `postgresql://...`(또는 구형 `postgres://`)를 준다. 비동기 엔진은 `+asyncpg` 가 필요하다.
    2. **libpq 전용 파라미터 제거** — `?sslmode=require` 같은 키를 asyncpg 는 모른다.
       그대로 두면 `connect() got an unexpected keyword argument` 로 죽는다.
       의미는 살려야 하므로 connect_args 의 `ssl` 로 옮긴다.

    Returns:
        (정규화된 URL, create_async_engine 에 넘길 connect_args)
    """
    url = (raw or "").strip()
    if not url:
        return "", {}

    parts = urlsplit(url)
    scheme = parts.scheme

    # postgres:// (구형 별칭) 와 드라이버 없는 postgresql:// 를 asyncpg 로 고정한다.
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    connect_args: dict[str, Any] = {}
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key not in _LIBPQ_ONLY_PARAMS:
            kept.append((key, value))
            continue
        if key == "sslmode":
            ssl_value = _SSLMODE_TO_ASYNCPG.get(value.strip().lower())
            if ssl_value is not None:
                connect_args["ssl"] = ssl_value

    normalized = urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))

    # urlunsplit 은 netloc 이 비면 `//` 를 떼 버린다. 호스트 없는 URL —
    # sqlite 의 `sqlite+aiosqlite:///./dev.db` 같은 것 — 이 `sqlite+aiosqlite:/./dev.db` 로
    # 망가져 SQLAlchemy 가 파싱을 거부한다. 원래 있던 `//` 는 그대로 살려 둔다.
    if not parts.netloc and url.startswith(f"{parts.scheme}://"):
        normalized = normalized.replace(f"{scheme}:", f"{scheme}://", 1)

    return normalized, connect_args


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "bullet-brak"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    max_rooms: int = 200
    room_idle_timeout_sec: int = 300

    #: 비어 있으면 DB 없이 인메모리로만 돈다(기존 동작). 계정/코인 영속화가 전부 꺼진다.
    database_url: str | None = None
    #: 기동 시 alembic upgrade head 를 돌릴지. 인스턴스가 1대라는 전제다(docs/DEPLOYMENT.md §2).
    db_auto_migrate: bool = True
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_echo: bool = False

    #: 계정 최초 생성 시 localStorage 잔액을 물려받을 수 있는 상한.
    #: 클라이언트가 보내는 값이라 위조 가능하다 — 기존 플레이어 이관용 유예 장치다.
    #: 이관이 끝나면 0 으로 내려서 창구를 닫는다.
    account_seed_coins_max: int = 100_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_enabled(self) -> bool:
        return bool((self.database_url or "").strip())

    @property
    def db_dsn(self) -> tuple[str, dict[str, Any]]:
        """(정규화된 URL, connect_args). `db_enabled` 가 False 면 ("", {})."""
        return normalize_database_url(self.database_url or "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
