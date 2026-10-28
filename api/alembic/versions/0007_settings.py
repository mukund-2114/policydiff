"""add the settings table: one row per workspace with model choices and encrypted provider keys

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28

`data` holds plain choices (which model each job uses, which reranker). `secrets` holds provider
keys, each one encrypted before it is written (app/services/secrets.py). A workspace with no row
uses models.yaml and the environment, exactly as before this change.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("secrets", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.UniqueConstraint("workspace_id", name="uq_settings_workspace"),
    )


def downgrade() -> None:
    op.drop_table("settings")
