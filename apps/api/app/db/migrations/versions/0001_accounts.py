"""계정 / 디바이스 토큰 / 아이템 소유권

Revision ID: 0001_accounts
Revises:
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_accounts"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 모델의 JSONVariant 와 동일 — Postgres 는 JSONB, 그 외는 JSON
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("nickname", sa.String(length=16), nullable=False),
        sa.Column("customization", _JSON, nullable=False),
        sa.Column("coins", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("matches_played", sa.Integer(), nullable=False),
        sa.Column("matches_won", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_last_seen_at", "accounts", ["last_seen_at"])

    op.create_table(
        "auth_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_auth_tokens_account_id", "auth_tokens", ["account_id"])

    op.create_table(
        "account_items",
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("item_key", sa.String(length=48), nullable=False),
        sa.Column("paid", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "item_key"),
    )


def downgrade() -> None:
    op.drop_table("account_items")
    op.drop_index("ix_auth_tokens_account_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_index("ix_accounts_last_seen_at", table_name="accounts")
    op.drop_table("accounts")
