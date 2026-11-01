import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import date
from types import SimpleNamespace as V

from app.services.versions import plan_supersede

TODAY = date(2026, 10, 24)


def v(label, status="ready", effective=None):
    return V(label=label, status=status, effective_from=effective)


def test_a_new_version_retires_the_ready_one_on_its_effective_date():
    old, new = v("1.0", effective=date(2025, 1, 1)), v("2.0", effective=date(2026, 3, 1))
    assert plan_supersede(new, [old], TODAY) == [(old, date(2026, 3, 1))]


def test_without_an_effective_date_the_end_date_is_today():
    old, new = v("1.0"), v("2.0")
    assert plan_supersede(new, [old], TODAY) == [(old, TODAY)]


def test_versions_that_are_not_ready_are_left_alone():
    failed, already = v("0.9", status="failed"), v("0.8", status="superseded")
    assert plan_supersede(v("2.0"), [failed, already], TODAY) == []


def test_an_older_upload_added_later_is_the_one_that_is_superseded():
    current = v("3.0", effective=date(2026, 6, 1))
    history = v("1.0", effective=date(2024, 1, 1))
    assert plan_supersede(history, [current], TODAY) == [(history, date(2026, 6, 1))]


def test_a_back_filled_version_ends_when_the_next_oldest_one_began():
    retired = v("2.0", status="superseded", effective=date(2025, 1, 1))
    current = v("3.0", effective=date(2026, 6, 1))
    history = v("1.0", effective=date(2024, 1, 1))
    assert plan_supersede(history, [retired, current], TODAY) == [(history, date(2025, 1, 1))]
