"""계정 로그인 — 아이디/비밀번호 + 인계 코드

Revision ID: 0002_account_login
Revises: 0001_accounts
Create Date: 2026-08-21

기존 계정은 넷 다 NULL 로 시작한다. 익명 계정이 여전히 기본이고, 로그인 수단은
사용자가 원할 때 얹는 선택지다 — 그래서 서버 기동만으로 아무도 잠기지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_account_login"
down_revision: str | None = "0001_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("login_id", sa.String(length=32), nullable=True))
    op.add_column("accounts", sa.Column("password_hash", sa.String(length=128), nullable=True))
    op.add_column("accounts", sa.Column("recovery_code_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("recovery_code_issued_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 둘 다 "이 값으로 계정을 찾는" 열이라 UNIQUE 여야 한다.
    # Postgres/sqlite 모두 NULL 은 여러 행이 가질 수 있으므로, 아직 안 만든 계정끼리는
    # 서로 부딪히지 않는다.
    op.create_index("ix_accounts_login_id", "accounts", ["login_id"], unique=True)
    op.create_index(
        "ix_accounts_recovery_code_hash", "accounts", ["recovery_code_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_accounts_recovery_code_hash", table_name="accounts")
    op.drop_index("ix_accounts_login_id", table_name="accounts")
    op.drop_column("accounts", "recovery_code_issued_at")
    op.drop_column("accounts", "recovery_code_hash")
    op.drop_column("accounts", "password_hash")
    op.drop_column("accounts", "login_id")
