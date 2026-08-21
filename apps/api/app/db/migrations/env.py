"""Alembic 실행 환경.

두 가지 경로를 모두 지원한다.

- **앱 기동 중**: `app.db.session.upgrade_to_head()` 가 이미 열린 커넥션을
  `config.attributes["connection"]` 으로 넘긴다. 엔진을 새로 만들지 않는다.
- **CLI**: `alembic revision --autogenerate` / `alembic upgrade head`.
  이때는 `app.config` 의 DATABASE_URL 을 읽어 async 엔진을 직접 만든다.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.db import models as _models  # noqa: F401  (metadata 등록용 — 지우지 말 것)

config = context.config

if config.config_file_name is not None and not config.attributes.get("connection"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> tuple[str, dict[str, object]]:
    settings = get_settings()
    if not settings.db_enabled:
        raise RuntimeError(
            "DATABASE_URL 이 비어 있다. apps/api/.env 에 설정하거나 환경변수로 넘길 것."
        )
    return settings.db_dsn


def run_migrations_offline() -> None:
    """`--sql` 모드. 실제 연결 없이 SQL 만 찍는다."""
    url, _ = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url, connect_args = _resolve_url()
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
            await connection.commit()
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    # 앱이 넘겨준 커넥션이 있으면 그대로 쓴다(트랜잭션도 앱 쪽이 관리).
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
