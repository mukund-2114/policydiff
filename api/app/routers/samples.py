"""Demo corpus endpoints. They answer 404 when the sample folder is not mounted."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app import auth
from app.models import User
from app.services import samples

router = APIRouter(prefix="/samples/northwind", tags=["samples"])


def _require_samples() -> None:
    if not samples.available():
        raise HTTPException(status_code=404, detail="Sample corpus is not installed")


@router.get("")
def status(user: User = Depends(auth.current_user)):
    return {"available": samples.available()}


@router.get("/policies")
def list_policies(user: User = Depends(auth.current_user)):
    _require_samples()
    return samples.policies()


@router.get("/policies/{doc_id}")
def get_policy(doc_id: str, user: User = Depends(auth.current_user)):
    _require_samples()
    found = samples.policy(doc_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return found


@router.get("/figures/{name}")
def get_figure(name: str, user: User = Depends(auth.current_user)):
    _require_samples()
    path = samples.figure_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Figure not found")
    return FileResponse(path, media_type="image/png")


@router.get("/answer-key")
def get_answer_key(user: User = Depends(auth.current_user)):
    _require_samples()
    return samples.answer_key()
