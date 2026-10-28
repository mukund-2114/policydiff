"""The Settings page: which model each job uses, which reranker, and the provider keys (D42).

Admin only. Keys are tested before they are saved, stored encrypted, and never sent back: the page
only learns whether a key is set and where it comes from. The audit log records which settings
changed, never their values.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db.session import get_db
from app.models import Settings, User
from app.providers import registry
from app.providers.base import ProviderError
from app.providers.check import check_key
from app.services import runtime, secrets
from app.services.preview import run_preview

router = APIRouter(tags=["settings"])

Provider = Literal["openai", "anthropic", "cohere"]


class ModelPick(BaseModel):
    provider: Literal["openai", "anthropic", "ollama"]
    model: str = Field(min_length=1, max_length=100)


class RerankPick(BaseModel):
    provider: Literal["local", "llm", "cohere"]
    model: str | None = Field(default=None, max_length=100)


class Choices(BaseModel):
    chat: ModelPick | None = None
    vision: ModelPick | None = None
    rerank: RerankPick | None = None


class SettingsIn(Choices):
    """Only what is sent changes. A key set to null is removed."""

    keys: dict[Provider, str | None] = {}


class KeyState(BaseModel):
    set: bool
    source: Literal["settings", "env"] | None  # where the key in use comes from


class SettingsOut(BaseModel):
    chat: ModelPick
    vision: ModelPick
    rerank: RerankPick
    embed: dict  # read-only: changing it means embedding every chunk again (D49)
    keys: dict[str, KeyState]
    allow_cloud: bool


class TestKeyIn(BaseModel):
    provider: Provider
    key: str | None = None  # leave out to test the key already in use


def _row(db: Session, user: User) -> Settings:
    row = db.scalars(select(Settings).where(Settings.workspace_id == user.workspace_id)).first()
    if row is None:
        row = Settings(workspace_id=user.workspace_id, data={}, secrets={})
        db.add(row)
        db.flush()
    return row


def _out() -> SettingsOut:
    cfg = registry.effective_config()
    base = registry.load_config()
    return SettingsOut(
        chat=ModelPick(provider=cfg.chat.provider, model=cfg.chat.model),
        vision=ModelPick(
            provider=(cfg.vision or cfg.chat).provider, model=(cfg.vision or cfg.chat).model
        ),
        rerank=RerankPick(provider=cfg.rerank.provider, model=cfg.rerank.model),
        embed={"provider": base.embed.provider, "model": base.embed.model, "dims": base.embed.dims},
        keys={
            p: KeyState(set=runtime.key_source(p) is not None, source=runtime.key_source(p))
            for p in runtime.ENV_KEYS
        },
        allow_cloud=cfg.egress.allow_cloud,
    )


def _needed_keys(data: dict) -> set[str]:
    """Providers whose key the chosen models and reranker will use."""
    picks = [data.get("chat"), data.get("vision")]
    need = {p["provider"] for p in picks if p and p["provider"] in runtime.ENV_KEYS}
    if (data.get("rerank") or {}).get("provider") == "cohere":
        need.add("cohere")
    return need


@router.get("/settings", response_model=SettingsOut)
def get_settings_page(_: User = Depends(auth.require_role("admin"))):
    return _out()


@router.put("/settings", response_model=SettingsOut)
def put_settings(
    body: SettingsIn,
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    row = _row(db, user)
    data = dict(row.data or {})
    for name in ("chat", "vision", "rerank"):
        if (pick := getattr(body, name)) is not None:
            data[name] = pick.model_dump()
    try:
        registry.effective_config(data)  # refuses a choice the egress rule does not allow
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    stored = dict(row.secrets or {})
    for provider, key in body.keys.items():
        if key is None or not key.strip():
            stored.pop(provider, None)
            continue
        ok, message = check_key(provider, key.strip())
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        stored[provider] = secrets.encrypt(key.strip())

    have = {
        p for p in runtime.ENV_KEYS if p in stored or getattr(get_settings(), runtime.ENV_KEYS[p])
    }
    for provider in sorted(_needed_keys(data) - have):
        raise HTTPException(status_code=400, detail=f"Add a {provider} key before choosing it.")

    row.data, row.secrets, row.updated_by = data, stored, user.id
    auth.audit(
        db,
        user,
        user.workspace_id,
        "settings_change",
        changed=sorted(
            [n for n in ("chat", "vision", "rerank") if getattr(body, n)]
            + [f"key:{k}" for k in body.keys]
        ),
    )
    db.commit()
    return _out()


@router.post("/settings/test-key")
def test_key(body: TestKeyIn, _: User = Depends(auth.require_role("admin"))):
    key = (body.key or "").strip() or runtime.secret(body.provider)
    if not key:
        return {"ok": False, "message": f"No {body.provider} key is set."}
    ok, message = check_key(body.provider, key)
    return {"ok": ok, "message": message}


@router.post("/settings/preview")
def preview(
    body: Choices,
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    """Run 20 random chunks through the funnel and the judge with these choices. Saves nothing."""
    data = runtime.stored_data()
    for name in ("chat", "vision", "rerank"):
        if (pick := getattr(body, name)) is not None:
            data[name] = pick.model_dump()
    try:
        cfg = registry.effective_config(data)
        result = run_preview(
            db, user.workspace_id, registry.get_chat(cfg), registry.get_reranker(cfg)
        )
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    auth.audit(db, user, user.workspace_id, "settings_preview", tokens=result["tokens"])
    db.commit()
    return result
