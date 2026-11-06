"""Allow multiple digest attempts per UTC run date.

Revision ID: 0002_multiple_digest_attempts
Revises: 0001_initial
Create Date: 2026-11-06
"""

from typing import Sequence

from alembic import op

revision: str = "0002_multiple_digest_attempts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_digests_run_date", "digests", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_digests_run_date", "digests", ["run_date"])
