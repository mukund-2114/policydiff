"""create the Procrastinate job queue tables inside our own database

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

The job queue lives in Postgres, so there is no Redis container. Procrastinate ships its own SQL
schema; this migration runs it once. After a Procrastinate upgrade, add a new migration with the
SQL from its migrations folder.
"""
from alembic import op
from procrastinate.schema import SchemaManager

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The SQL contains % characters, which the driver would read as placeholders, so double them.
    op.get_bind().exec_driver_sql(SchemaManager.get_schema().replace("%", "%%"))


def downgrade() -> None:
    # Drops the tables only. The helper functions and types Procrastinate created stay behind.
    for table in ("procrastinate_events", "procrastinate_periodic_defers", "procrastinate_jobs", "procrastinate_workers"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
