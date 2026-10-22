"""The background job queue. Jobs are rows in our own Postgres (Procrastinate), so no Redis.

Two sides use it:
  - the worker container runs `python -m procrastinate --app=app.jobs.queue worker` and does the jobs;
  - the api process only adds jobs. It swaps in a plain synchronous connection while it runs
    (open_for_api, called from main.py), because FastAPI endpoints here are ordinary functions.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from procrastinate import App, PsycopgConnector, SyncPsycopgConnector

from app.config import get_settings


def _conninfo() -> str:
    # SQLAlchemy URLs carry the driver name (postgresql+psycopg). psycopg wants the plain form.
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


queue = App(connector=PsycopgConnector(conninfo=_conninfo()), import_paths=["app.tasks"])


@contextmanager
def open_for_api() -> Iterator[None]:
    import app.tasks  # noqa: F401  makes sure the tasks are registered on `queue`

    with queue.replace_connector(SyncPsycopgConnector(conninfo=_conninfo())) as q, q.open():
        yield


def enqueue_parse(version_id: uuid.UUID) -> None:
    queue.configure_task("parse_version").defer(version_id=str(version_id))
