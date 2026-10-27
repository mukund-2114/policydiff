import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from pydantic import ValidationError

from app.routers.findings import FindingUpdate


def test_only_the_fields_that_are_sent_count_as_changes():
    body = FindingUpdate(status="dismissed", resolution_note="Different teams")
    assert body.model_dump(exclude_unset=True) == {
        "status": "dismissed",
        "resolution_note": "Different teams",
    }


def test_an_owner_can_be_cleared_by_sending_null():
    assert FindingUpdate(owner=None).model_dump(exclude_unset=True) == {"owner": None}


def test_an_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        FindingUpdate(status="maybe")
