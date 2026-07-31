"""환경변수 기반 설정. `.env.sample` 참고."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "bullet-brak"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    max_rooms: int = 200
    room_idle_timeout_sec: int = 300

    # 추후 DB 연동 지점
    database_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
