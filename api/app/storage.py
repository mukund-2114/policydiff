"""Where uploaded files and parser output live.

Everything else in the app asks this module to save or fetch a file by key, for example
"originals/<version id>.pdf". Only here do we know whether the bytes sit in a local folder or in an
S3-compatible bucket (AWS S3, MinIO, Cloudflare R2). The database stores the key, never a path.
"""

import shutil
import uuid
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings

CHUNK = 1024 * 1024


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def stream(self, key: str) -> Iterator[bytes]:
        """The file in pieces, so a large PDF is never held in memory by the api."""
        ...

    def download(self, key: str, dest: Path) -> None:
        """Copy the file to a local path. The parser needs a real file on disk."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Remove the file. A file that is already gone is not an error."""
        ...


class LocalStorage:
    """A folder on disk. The default, and what the unit tests use."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # a key must never climb out of the folder
            raise ValueError(f"Bad storage key: {key}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def stream(self, key: str) -> Iterator[bytes]:
        with self._path(key).open("rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    def download(self, key: str, dest: Path) -> None:
        shutil.copyfile(self._path(key), dest)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """An S3-compatible bucket. The bucket must already exist (Compose creates one for MinIO).

    With no access key set, boto3 finds credentials itself (environment, shared config, or the
    IAM role of the machine), which is what you want on AWS.
    """

    def __init__(
        self, bucket: str, endpoint_url: str, region: str, access_key: str, secret_key: str
    ):
        import boto3  # imported here so the local adapter works without it being configured

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,  # empty means real AWS
            region_name=region or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def stream(self, key: str) -> Iterator[bytes]:
        yield from self.client.get_object(Bucket=self.bucket, Key=key)["Body"].iter_chunks(CHUNK)

    def download(self, key: str, dest: Path) -> None:
        self.client.download_file(self.bucket, key, str(dest))

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise  # a permissions or network problem should not look like "file missing"
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)  # S3 does not mind a missing key


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage(
            s.s3_bucket, s.s3_endpoint_url, s.s3_region, s.s3_access_key, s.s3_secret_key
        )
    if s.storage_backend == "local":
        return LocalStorage(s.files_dir)
    raise ValueError(f"STORAGE_BACKEND must be 'local' or 's3', not '{s.storage_backend}'")


def original_key(version_id: uuid.UUID) -> str:
    return f"originals/{version_id}.pdf"


def parsed_key(version_id: uuid.UUID) -> str:
    return f"parsed/{version_id}.json"
