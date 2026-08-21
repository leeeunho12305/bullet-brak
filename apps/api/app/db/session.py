"""엔진/세션 수명주기.

핵심 규칙 두 가지.

1. **DB 는 없어도 된다.** `DATABASE_URL` 이 없으면 엔진을 만들지 않고 `db_ready()` 가
   False 를 돌려준다. 호출부는 그 경우 DB 를 쓰는 기능만 조용히 비활성화한다.
2. **DB 장애가 게임을 죽이면 안 된다.** 기동 시 연결에 실패해도 예외를 올리지 않고
   경고만 남긴 뒤 DB 없는 모드로 계속 뜬다. 방/매치는 원래 메모리에만 있으므로
   DB 가 죽어도 게임 자체는 굴러가야 한다.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

#: apps/api/alembic.ini
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def db_ready() -> bool:
    """엔진이 살아 있어서 DB 를 써도 되는 상태인가."""
    return _sessionmaker is not None


def engine() -> AsyncEngine | None:
    return _engine


async def init_db(settings: Settings | None = None) -> bool:
    """엔진 생성 + (설정 시) 마이그레이션. 성공하면 True.

    실패해도 예외를 올리지 않는다 — DB 없는 모드로 떨어질 뿐이다.
    """
    global _engine, _sessionmaker

    settings = settings or get_settings()
    if not settings.db_enabled:
        logger.info("DATABASE_URL 없음 — 인메모리 모드로 기동한다(계정/코인 영속화 꺼짐).")
        return False

    url, connect_args = settings.db_dsn
    try:
        _engine = create_async_engine(
            url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,  # 유휴 커넥션이 끊긴 뒤 첫 쿼리가 죽는 것 방지
            connect_args=connect_args,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    except Exception:
        logger.exception("DB 엔진 생성 실패 — 인메모리 모드로 계속한다.")
        _engine, _sessionmaker = None, None
        return False

    if settings.db_auto_migrate:
        try:
            await upgrade_to_head()
        except Exception:
            logger.exception("마이그레이션 실패 — 인메모리 모드로 계속한다.")
            await dispose_engine()
            return False

    logger.info("DB 연결 완료 (%s)", _safe_dsn(url))
    return True


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        with contextlib.suppress(Exception):
            await _engine.dispose()
    _engine, _sessionmaker = None, None


async def upgrade_to_head() -> None:
    """`alembic upgrade head` 를 이미 열린 async 커넥션 위에서 실행한다.

    별도 프로세스로 alembic 을 부르면 Render·Dokploy·로컬에서 각각 실행 지점을
    따로 만들어 줘야 한다. 기동 시 앱이 직접 돌리면 배포처가 어디든 동일하게 동작한다.

    ⚠ 인스턴스가 2대 이상이면 동시에 마이그레이션이 돌 수 있다. 이 프로젝트는
      방 상태가 프로세스 메모리에 있어 replicas=1 고정이라 문제가 되지 않는다.
      확장하게 되면 `DB_AUTO_MIGRATE=false` 로 끄고 배포 파이프라인에서 한 번만 돌릴 것.
    """
    if _engine is None:
        return

    from alembic import command
    from alembic.config import Config

    def _run(connection: object) -> None:
        cfg = Config(str(ALEMBIC_INI))
        # env.py 가 이 커넥션을 그대로 쓴다(엔진을 새로 만들지 않는다).
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    async with _engine.begin() as conn:
        await conn.run_sync(_run)


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """쓰기용 세션. 정상 종료 시 커밋, 예외 시 롤백.

    `db_ready()` 가 False 인데 호출하면 RuntimeError — 호출 전에 반드시 확인할 것.
    """
    if _sessionmaker is None:
        raise RuntimeError("DB 가 비활성 상태다. db_ready() 를 먼저 확인할 것.")
    session = _sessionmaker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _safe_dsn(url: str) -> str:
    """로그에 비밀번호가 찍히지 않도록 가린다."""
    if "@" not in url:
        return url
    head, tail = url.rsplit("@", 1)
    if ":" not in head:
        return f"***@{tail}"
    return f"{head.rsplit(':', 1)[0]}:***@{tail}"


def _install_for_tests(sessionmaker: async_sessionmaker[AsyncSession], eng: AsyncEngine) -> None:
    """테스트가 sqlite 엔진을 꽂을 때 쓰는 뒷문. 운영 코드에서는 부르지 않는다."""
    global _engine, _sessionmaker
    _engine, _sessionmaker = eng, sessionmaker
