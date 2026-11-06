"""Create initial digest database schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-06
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", name="uq_sources_channel_id"),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_language", sa.String(length=32), nullable=True),
        sa.Column("transcript_is_generated", sa.Boolean(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", name="uq_articles_video_id"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_table(
        "digests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'failed', 'empty')",
            name="ck_digests_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_date", name="uq_digests_run_date"),
    )


def downgrade() -> None:
    op.drop_table("digests")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_table("articles")
    op.drop_table("sources")
