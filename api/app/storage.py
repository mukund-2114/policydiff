"""Where uploaded files and parser output live on disk. One place, so paths never drift."""

import uuid
from pathlib import Path

from app.config import get_settings


def originals_path(version_id: uuid.UUID) -> Path:
    return Path(get_settings().files_dir) / "originals" / f"{version_id}.pdf"


def parsed_path(version_id: uuid.UUID) -> Path:
    return Path(get_settings().files_dir) / "parsed" / f"{version_id}.json"
