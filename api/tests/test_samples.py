import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest

from app.services import samples


@pytest.mark.parametrize(
    "bad", ["../secret", "..\\secret", "TRV-001/../../x", "trv-001", "TRV-1", ""]
)
def test_policy_ids_that_are_not_the_exact_shape_are_refused(bad):
    # The id becomes part of a file path, so anything but ABC-123 must be rejected first.
    assert samples.policy(bad) is None


@pytest.mark.parametrize("bad", ["../x.png", "a/b.png", "x.txt", "X.png", ""])
def test_figure_names_that_are_not_plain_png_names_are_refused(bad):
    assert samples.figure_path(bad) is None
