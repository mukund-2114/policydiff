from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db.session import get_db
from app.models import User

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


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = auth.verify_password(user.password_hash if user else _DUMMY_HASH, body.password)
    if not user or not ok:
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
