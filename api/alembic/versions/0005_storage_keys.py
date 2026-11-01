"""store storage keys instead of absolute paths

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22

Files are now found by key ("originals/<id>.pdf") through the storage adapter, so the same row
works for a local folder and for a bucket. Older rows held the full path under /data/files.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PREFIX = "/data/files/"


def upgrade() -> None:
    for column in ("file_path", "parsed_json_path"):
        op.execute(
            f"UPDATE document_version SET {column} = substr({column}, {len(PREFIX) + 1}) "
            f"WHERE {column} LIKE '{PREFIX}%'"
        )


def downgrade() -> None:
    for column in ("file_path", "parsed_json_path"):
        op.execute(
            f"UPDATE document_version SET {column} = '{PREFIX}' || {column} "
            f"WHERE {column} IS NOT NULL AND {column} NOT LIKE '/%'"
        )
