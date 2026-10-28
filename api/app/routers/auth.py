from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db.session import get_db
from app.models import AuditEvent, User, Workspace

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash checked when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = auth.hash_password("not-a-real-password")


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str


MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


def _locked_out(db: Session, email: str) -> bool:
    """Five failed sign-ins for one address in 15 minutes block further tries for that address.

    The count comes from the audit log, so it needs no extra table and survives a restart. A
    correct password does not clear it, which keeps a guesser from learning when they hit the right
    one.
    """
    since = datetime.now(UTC) - LOCKOUT
    failures = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "login_failed",
            AuditEvent.created_at >= since,
            AuditEvent.detail["email"].astext == email[:100],
        )
    )
    return (failures or 0) >= MAX_FAILED_LOGINS


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = auth.verify_password(user.password_hash if user else _DUMMY_HASH, body.password)
    email = body.email.strip().lower()
    if _locked_out(db, email):
        raise HTTPException(
            status_code=429, detail="Too many failed sign-ins. Try again in 15 minutes."
        )
    if not user or not ok:
        ws = user.workspace_id if user else db.scalar(select(Workspace.id).limit(1))
        if ws:
            auth.audit(db, None, ws, "login_failed", email=email[:100])
            db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    s = get_settings()
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_session_token(user.id),
        max_age=s.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
    )
    auth.audit(db, user, user.workspace_id, "login")
    db.commit()
    return UserOut(id=str(user.id), email=user.email, role=user.role)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth.current_user)):
    return UserOut(id=str(user.id), email=user.email, role=user.role)
