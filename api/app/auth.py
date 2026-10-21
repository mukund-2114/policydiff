import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.models import AuditEvent, User, Workspace

COOKIE_NAME = "pd_session"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def make_session_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps(str(user_id))


def read_session_token(token: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(
            _serializer().loads(token, max_age=get_settings().session_max_age_seconds)
        )
    except (BadSignature, ValueError):
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = read_session_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Not allowed")
        return user

    return dep


def audit(db: Session, user: User | None, workspace_id: uuid.UUID, action: str, **detail) -> None:
    db.add(
        AuditEvent(
            workspace_id=workspace_id,
            user_id=user.id if user else None,
            action=action,
            detail=detail or None,
        )
    )


def bootstrap_admin(db: Session) -> None:
    """Create the workspace and first admin when the database has no users."""
    s = get_settings()
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    if not s.admin_email or not s.admin_password:
        return
    ws = Workspace(name="Default")
    db.add(ws)
    db.flush()
    db.add(
        User(
            workspace_id=ws.id,
            email=s.admin_email.lower(),
            password_hash=hash_password(s.admin_password),
            role="admin",
        )
    )
    audit(db, None, ws.id, "bootstrap_admin", email=s.admin_email.lower())
    db.commit()
