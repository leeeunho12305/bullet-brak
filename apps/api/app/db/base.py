"""모든 ORM 모델의 공통 베이스.

`models` 를 import 하지 않는다 — alembic env.py 가 순환 없이 metadata 를 집어갈 수 있어야 한다.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
