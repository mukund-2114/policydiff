"""Encrypt provider keys before they are stored (decision Q9, D42).

The key is derived from SECRET_KEY, so a database dump alone does not reveal the provider keys, and
nothing extra has to be set up. If SECRET_KEY changes, the stored keys cannot be read any more:
`decrypt` returns None and the app falls back to the environment, and an admin enters them again.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"policydiff-settings:{get_settings().secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
