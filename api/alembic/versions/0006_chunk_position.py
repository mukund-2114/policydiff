"""add chunk.position so chunks keep their order in the document

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24

Row ids are time-ordered but not guaranteed to be in insert order inside one batch, so the order
is stored on purpose. The chunk table is empty at this point (chunking arrives with this change).
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunk", sa.Column("position", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("chunk", "position")
