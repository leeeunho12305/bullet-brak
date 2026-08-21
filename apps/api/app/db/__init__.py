"""DB 레이어 — Postgres + SQLAlchemy 2.0(async) + Alembic.

**DB 는 선택 사항이다.** `DATABASE_URL` 이 비어 있으면 엔진을 아예 만들지 않고,
서버는 예전처럼 순수 인메모리로 돈다(계정/코인 영속화만 꺼진다). 테스트와
"DB 없이 잠깐 띄우기"가 계속 가능해야 해서 이렇게 뒀다.

구성:
- `base`    : DeclarativeBase
- `models`  : Account / AuthToken / AccountItem
- `session` : 엔진·세션 수명주기와 마이그레이션 실행

**게임 루프에서는 이 패키지를 건드리지 않는다.** 60Hz 틱 안에 `await db` 가 끼면
틱이 밀린다. DB 접근은 접속(join)·REST·매치 종료 같은 저빈도 지점에서만 한다.
자세한 내용은 docs/DEPLOYMENT.md Phase 4.
"""

from app.db.base import Base
from app.db.session import db_ready, dispose_engine, init_db, session_scope

__all__ = ["Base", "db_ready", "dispose_engine", "init_db", "session_scope"]
