"""경쟁전 — 시즌 / 랭크 프로필 / 매치 기록

Revision ID: 0003_ranked
Revises: 0002_account_login
Create Date: 2026-08-22

기존 계정은 아무것도 잃지 않는다. 랭크는 `rank_profiles` 에 따로 쌓이고, 그 행은
경쟁전을 처음 눌렀을 때 만들어진다 — 즉 이 마이그레이션만으로는 누구도 랭커가 되지 않는다.

첫 시즌("액트 1")은 여기서 만들어 둔다. 서버가 기동할 때 활성 시즌을 찾는데,
없으면 그때 만들기는 하지만 마이그레이션에서 넣어 두면 시즌 id 가 어느 배포에서나 1 이다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ranked"
down_revision: str | None = "0002_account_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seasons = op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_seasons_key"),
    )
    op.create_index("ix_seasons_is_active", "seasons", ["is_active"])

    op.create_table(
        "rank_profiles",
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("mmr", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("rr", sa.Integer(), nullable=False),
        sa.Column("placements", sa.Integer(), nullable=False),
        sa.Column("shield", sa.Boolean(), nullable=False),
        sa.Column("peak_tier", sa.Integer(), nullable=False),
        sa.Column("peak_rr", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("streak", sa.Integer(), nullable=False),
        sa.Column("best_streak", sa.Integer(), nullable=False),
        sa.Column("rounds_won", sa.Integer(), nullable=False),
        sa.Column("rounds_lost", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "season_id"),
    )
    # 리더보드가 이 인덱스 하나로 끝난다(활성 시즌 + 티어·RR 내림차순 = 순위).
    op.create_index(
        "ix_rank_profiles_leaderboard",
        "rank_profiles",
        ["season_id", sa.text("tier DESC"), sa.text("rr DESC")],
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("ranked", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("room_code", sa.String(length=8), nullable=False),
        sa.Column("map_id", sa.String(length=32), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.Column("winner_account_id", sa.String(length=32), nullable=True),
        sa.Column("forfeit", sa.Boolean(), nullable=False),
        sa.Column(
            "ended_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="SET NULL"),
        # 계정이 지워져도 매치 행은 남는다 — 상대의 전적에서 그 판이 사라지면 안 된다.
        sa.ForeignKeyConstraint(["winner_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_ended_at", "matches", [sa.text("ended_at DESC")])
    op.create_index(
        "ix_matches_ranked_ended_at", "matches", ["ranked", sa.text("ended_at DESC")]
    )

    op.create_table(
        "match_participants",
        sa.Column("match_id", sa.String(length=32), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=True),
        sa.Column("nickname", sa.String(length=16), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("opponent_score", sa.Integer(), nullable=False),
        sa.Column("coins_earned", sa.Integer(), nullable=False),
        sa.Column("tier_before", sa.Integer(), nullable=False),
        sa.Column("rr_before", sa.Integer(), nullable=False),
        sa.Column("tier_after", sa.Integer(), nullable=False),
        sa.Column("rr_after", sa.Integer(), nullable=False),
        sa.Column("rr_delta", sa.Integer(), nullable=False),
        sa.Column("placement", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        # 비로그인 참가자도 남겨야 해서 account_id 는 키가 될 수 없다.
        sa.PrimaryKeyConstraint("match_id", "slot"),
    )
    op.create_index("ix_match_participants_account_id", "match_participants", ["account_id"])

    op.bulk_insert(
        seasons,
        [{"key": "act-1", "name": "액트 1", "ended_at": None, "is_active": True}],
    )


def downgrade() -> None:
    op.drop_index("ix_match_participants_account_id", table_name="match_participants")
    op.drop_table("match_participants")
    op.drop_index("ix_matches_ranked_ended_at", table_name="matches")
    op.drop_index("ix_matches_ended_at", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_rank_profiles_leaderboard", table_name="rank_profiles")
    op.drop_table("rank_profiles")
    op.drop_index("ix_seasons_is_active", table_name="seasons")
    op.drop_table("seasons")
