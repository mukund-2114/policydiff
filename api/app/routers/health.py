from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.providers import registry
from app.providers.base import Message

router = APIRouter(tags=["health"])


@router.get("/health")
def health(deep: bool = False, db: Session = Depends(get_db)):
    """Shallow check is free. deep=true makes one tiny call to the chat and embedding providers."""
    result: dict = {"status": "ok", "db": "ok", "pgvector": "ok", "models": {}}
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"))
        if not has_vector:
            result["pgvector"] = "missing"
            result["status"] = "degraded"
    except Exception as exc:  # noqa: BLE001
        result.update(status="down", db=f"error: {type(exc).__name__}")
        return result

    try:
        cfg = registry.load_config()
        result["models"] = {
            "chat": f"{cfg.chat.provider}:{cfg.chat.model}",
            "embed": f"{cfg.embed.provider}:{cfg.embed.model}",
            "allow_cloud": cfg.egress.allow_cloud,
        }
        chat = registry.get_chat()
        embedder = registry.get_embedder()
        result["models"]["keys"] = "present"
        if deep:
            chat.generate([Message("user", "Reply with the word ok.")])
            embedder.embed(["ok"])
            result["models"]["reachable"] = True
    except Exception as exc:  # noqa: BLE001
        result["status"] = "degraded"
        result["models"]["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return result
