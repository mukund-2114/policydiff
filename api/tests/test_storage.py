import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import io
import uuid

import pytest
from botocore.exceptions import ClientError

from app import storage
from app.storage import LocalStorage, S3Storage


def test_local_storage_round_trip(tmp_path):
    store = LocalStorage(str(tmp_path / "files"))
    assert not store.exists("originals/a.pdf")
    store.put("originals/a.pdf", b"%PDF-1.7 hello")
    assert store.exists("originals/a.pdf")
    assert store.get("originals/a.pdf") == b"%PDF-1.7 hello"
    assert b"".join(store.stream("originals/a.pdf")) == b"%PDF-1.7 hello"
    store.download("originals/a.pdf", tmp_path / "copy.pdf")
    assert (tmp_path / "copy.pdf").read_bytes() == b"%PDF-1.7 hello"


def test_local_storage_rejects_keys_that_leave_the_folder(tmp_path):
    store = LocalStorage(str(tmp_path / "files"))
    with pytest.raises(ValueError, match="Bad storage key"):
        store.put("../outside.txt", b"x")


def test_keys_are_named_after_the_version():
    vid = uuid.uuid4()
    assert storage.original_key(vid) == f"originals/{vid}.pdf"
    assert storage.parsed_key(vid) == f"parsed/{vid}.json"


class FakeS3Client:
    """Stands in for boto3 so the test needs no network and no MinIO."""

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        body = io.BytesIO(self.objects[(Bucket, Key)])
        body.iter_chunks = lambda size: iter([body.read(size)])
        return {"Body": body}

    def head_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


def test_s3_storage_round_trip_and_missing_file():
    store = S3Storage("b", "http://localhost:9000", "us-east-1", "k", "s")
    store.client = FakeS3Client()
    assert not store.exists("x")
    store.put("x", b"data")
    assert store.exists("x")
    assert store.get("x") == b"data"
    assert b"".join(store.stream("x")) == b"data"


def test_s3_storage_does_not_hide_other_errors():
    store = S3Storage("b", "", "", "", "")
    client = FakeS3Client()

    def denied(Bucket, Key):  # noqa: N803
        raise ClientError({"Error": {"Code": "403"}}, "HeadObject")

    client.head_object = denied
    store.client = client
    with pytest.raises(ClientError):
        store.exists("x")


def test_local_storage_delete_removes_the_file_and_ignores_a_missing_one(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put("a.txt", b"x")
    store.delete("a.txt")
    assert not store.exists("a.txt")
    store.delete("a.txt")  # already gone: no error
