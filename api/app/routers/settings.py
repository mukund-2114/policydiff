"""The Settings page: which model each job uses, which reranker, and the provider keys (D42).

Admin only. Keys are tested before they are saved, stored encrypted, and never sent back: the page
only learns whether a key is set and where it comes from. The audit log records which settings
changed, never their values.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db.session import get_db
from app.models import Chunk, DocumentVersion, Settings, User
from app.providers import registry
from app.providers.base import ProviderError
from app.providers.check import check_key
from app.providers.model_list import list_models
from app.services import params, runtime, secrets
from app.services.preview import run_preview

router = APIRouter(tags=["settings"])

Provider = Literal["openai", "anthropic", "cohere"]


class ModelPick(BaseModel):
    provider: Literal["openai", "openai_compatible", "anthropic", "bedrock", "ollama"]
    model: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=300)  # openai_compatible and ollama


class EmbedPick(BaseModel):
    provider: Literal["openai", "openai_compatible", "ollama"]
    model: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=300)


class RerankPick(BaseModel):
    provider: Literal["local", "llm", "cohere"]
    model: str | None = Field(default=None, max_length=100)


class Choices(BaseModel):
    chat: ModelPick | None = None
    vision: ModelPick | None = None
    rerank: RerankPick | None = None
    pipeline: dict[str, float | str] | None = (
        None  # search and ranking numbers (services/params.py)
    )


class SettingsIn(Choices):
    """Only what is sent changes. A key set to null is removed."""

    keys: dict[Provider, str | None] = {}
    embed: EmbedPick | None = None  # a new model means every chunk is embedded again (D56)


class KeyState(BaseModel):
    set: bool
    source: Literal["settings", "env"] | None  # where the key in use comes from


class SettingsOut(BaseModel):
    chat: ModelPick
    vision: ModelPick
    rerank: RerankPick
    pipeline: list[dict]  # one entry per number: value, default, range, what changing it does
    embed: dict  # provider, model and the fixed vector size
    embed_stale: int  # chunks still embedded with another model than the one chosen
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


def _stale_chunks(db: Session, model: str) -> int:
    """Chunks of searchable versions whose vector came from a different model."""
    return (
        db.scalar(
            select(func.count(Chunk.id))
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .where(
                DocumentVersion.status.in_(["ready", "superseded"]),
                Chunk.embedding_model.is_distinct_from(model),
            )
        )
        or 0
    )


def _out(db: Session) -> SettingsOut:
    cfg = registry.effective_config()
    return SettingsOut(
        chat=ModelPick(
            provider=cfg.chat.provider, model=cfg.chat.model, base_url=cfg.chat.base_url
        ),
        vision=ModelPick(
            provider=(cfg.vision or cfg.chat).provider,
            model=(cfg.vision or cfg.chat).model,
            base_url=(cfg.vision or cfg.chat).base_url,
        ),
        rerank=RerankPick(provider=cfg.rerank.provider, model=cfg.rerank.model),
        pipeline=params.describe(params.get_params()),
        embed={
            "provider": cfg.embed.provider,
            "model": cfg.embed.model,
            "dims": cfg.embed.dims,
            "base_url": cfg.embed.base_url,
        },
        embed_stale=_stale_chunks(db, cfg.embed.model),
        keys={
            p: KeyState(set=runtime.key_source(p) is not None, source=runtime.key_source(p))
            for p in runtime.ENV_KEYS
        },
        allow_cloud=cfg.egress.allow_cloud,
    )


def _needed_keys(data: dict) -> set[str]:
    """Providers whose key the chosen models and reranker will use."""
    picks = [data.get("chat"), data.get("vision"), data.get("embed")]
    need = {p["provider"] for p in picks if p and p["provider"] in runtime.ENV_KEYS}
    if (data.get("rerank") or {}).get("provider") == "cohere":
        need.add("cohere")
    return need


@router.get("/settings", response_model=SettingsOut)
def get_settings_page(_: User = Depends(auth.require_role("admin")), db: Session = Depends(get_db)):
    return _out(db)


@router.put("/settings", response_model=SettingsOut)
def put_settings(
    body: SettingsIn,
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    row = _row(db, user)
    data = dict(row.data or {})
    for name in ("chat", "vision", "rerank", "embed"):
        if (pick := getattr(body, name)) is not None:
            data[name] = pick.model_dump()
    if body.pipeline is not None:
        try:
            data["pipeline"] = params.clean(body.pipeline, strict=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
    # Built after every choice is in `data`, so the egress check and the embedding probe below
    # test what is about to be saved and not what was saved before.
    try:
        cfg = registry.effective_config(data)  # refuses a choice the egress rule does not allow
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

    if body.embed is not None:
        _probe_embedder(cfg)  # one tiny call, so a model that cannot give 1536 numbers is refused

    row.data, row.secrets, row.updated_by = data, stored, user.id
    auth.audit(
        db,
        user,
        user.workspace_id,
        "settings_change",
        changed=sorted(
            [
                n
                for n in ("chat", "vision", "rerank", "embed", "pipeline")
                if getattr(body, n) is not None
            ]
            + [f"key:{k}" for k in body.keys]
        ),
    )
    db.commit()
    return _out(db)


def _probe_embedder(cfg) -> None:
    """Embed one word with the chosen model and check the vector has the size the database holds."""
    try:
        vector = registry.get_embedder(cfg).embed(["test"])[0]
    except Exception as e:  # noqa: BLE001 - any provider failure means the choice cannot be used
        raise HTTPException(
            status_code=400, detail=f"The embedding model did not answer: {str(e)[:200]}"
        ) from None
    if len(vector) != cfg.embed.dims:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This model returns {len(vector)} numbers per vector; "
                f"the database holds {cfg.embed.dims}."
            ),
        )


@router.get("/settings/models")
def models(
    provider: Literal["openai", "openai_compatible", "anthropic", "bedrock", "ollama"],
    job: Literal["chat", "vision", "embed"] = "chat",
    base_url: str | None = None,
    _: User = Depends(auth.require_role("admin")),
):
    """The models a provider offers for a job, for the dropdowns. Empty, with a reason, if none."""
    egress = registry.load_config().egress
    if not egress.allow_cloud and (
        provider in registry.CLOUD_PROVIDERS or not registry._is_private(base_url)
    ):
        return {"models": [], "message": "Cloud providers are switched off by egress.allow_cloud."}
    key = runtime.secret(provider) if provider in runtime.ENV_KEYS else ""
    if provider == "openai_compatible":
        key = runtime.secret("openai")
    found, message = list_models(provider, job, key, base_url)
    return {"models": found, "message": message}


@router.post("/settings/embed/reindex", response_model=SettingsOut)
def reindex(
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    """Embed every searchable version again with the chosen model. Queues one job per version."""
    versions = db.scalars(
        select(DocumentVersion).where(
            DocumentVersion.workspace_id == user.workspace_id,
            # A version whose last embedding failed is retried too, so one bad try cannot leave
            # a document out of search for good.
            or_(
                DocumentVersion.status.in_(["ready", "superseded"]),
                (DocumentVersion.status == "failed")
                & (DocumentVersion.failed_stage == "embedding"),
            ),
        )
    ).all()
    from app.jobs import enqueue_embed  # here, so importing this module needs no job queue

    try:
        for v in versions:
            enqueue_embed(v.id)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Could not queue the jobs.") from None
    auth.audit(db, user, user.workspace_id, "reindex_start", versions=len(versions))
    db.commit()
    return _out(db)


@router.post("/settings/pipeline/reset", response_model=SettingsOut)
def reset_pipeline(
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    """Put every search and ranking number back to its default. Models and keys are not touched."""
    row = _row(db, user)
    data = dict(row.data or {})
    data.pop("pipeline", None)
    row.data, row.updated_by = data, user.id
    auth.audit(db, user, user.workspace_id, "settings_reset", changed=["pipeline"])
    db.commit()
    return _out(db)


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
        if body.pipeline is not None:
            data["pipeline"] = params.clean(body.pipeline, strict=True)
        cfg = registry.effective_config(data)
        result = run_preview(
            db,
            user.workspace_id,
            registry.get_chat(cfg),
            registry.get_reranker(cfg),
            params.get_params(data),
            registry.get_embedder(),
            registry.get_chat(cfg, fast=True),
        )
    except (ProviderError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    auth.audit(db, user, user.workspace_id, "settings_preview", tokens=result["tokens"])
    db.commit()
    return result
