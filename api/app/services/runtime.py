"""What the app is set to use now: the settings row first, then models.yaml and the environment.

The api and the worker both read this, each time a job starts, so a change made on the Settings
page applies to the next scan without restarting anything. A workspace with no settings row behaves
exactly as before the Settings page existed.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine
from app.models import Settings
from app.services import secrets

log = logging.getLogger(__name__)

# Provider name -> the setting in .env that holds its key.
ENV_KEYS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "cohere": "cohere_api_key",
}


def _row() -> Settings | None:
    # There is one workspace for now, so the first settings row is the one. A multi-team setup
    # would pass the workspace id in.
    try:
        with Session(get_engine()) as db:
            row = db.scalars(select(Settings).limit(1)).first()
            if row:
                db.expunge(row)
            return row
    except Exception:  # noqa: BLE001 - the database being down must not hide the env fallback
        log.warning("could not read the settings table; using models.yaml and the environment")
        return None


def stored_data() -> dict:
    row = _row()
    return dict(row.data or {}) if row else {}


def stored_key(provider: str) -> str | None:
    row = _row()
    token = (row.secrets or {}).get(provider) if row else None
    return secrets.decrypt(token) if token else None


def secret(provider: str) -> str:
    """The key for a provider: the one saved on the Settings page, else the one in .env."""
    return stored_key(provider) or getattr(get_settings(), ENV_KEYS[provider])


def key_source(provider: str) -> str | None:
    if stored_key(provider):
        return "settings"
    return "env" if getattr(get_settings(), ENV_KEYS[provider]) else None
