import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import date

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.providers import registry
from app.providers.base import ProviderError
from app.providers.registry import ChatCfg, EgressCfg, EmbedCfg, ModelsConfig
from app.retrieval.search import _scope
from app.routers.settings import SettingsIn, _needed_keys
from app.services import runtime, secrets


def base_cfg(allow_cloud=True):
    return ModelsConfig(
        chat=ChatCfg(provider="openai", model="m1"),
        embed=EmbedCfg(provider="openai", model="e", dims=8),
        egress=EgressCfg(allow_cloud=allow_cloud),
    )


def use(monkeypatch, cfg, stored):
    monkeypatch.setattr(registry, "load_config", lambda: cfg)
    monkeypatch.setattr(runtime, "stored_data", lambda: stored)


def test_a_key_is_not_stored_in_the_clear():
    token = secrets.encrypt("sk-abc123")
    assert "sk-abc123" not in token
    assert secrets.decrypt(token) == "sk-abc123"


def test_a_key_stored_under_another_secret_cannot_be_read(monkeypatch):
    token = secrets.encrypt("sk-abc123")
    monkeypatch.setattr(get_settings(), "secret_key", "a-different-secret")
    assert secrets.decrypt(token) is None


def test_the_saved_choice_wins_over_models_yaml(monkeypatch):
    use(monkeypatch, base_cfg(), {"chat": {"provider": "anthropic", "model": "claude-x"}})
    cfg = registry.effective_config()
    assert (cfg.chat.provider, cfg.chat.model) == ("anthropic", "claude-x")


def test_with_nothing_saved_models_yaml_is_used(monkeypatch):
    use(monkeypatch, base_cfg(), {})
    assert registry.effective_config().chat.model == "m1"


def test_a_choice_that_breaks_the_egress_rule_is_refused(monkeypatch):
    use(monkeypatch, base_cfg(allow_cloud=False), {})
    with pytest.raises(ProviderError):
        registry.effective_config({"rerank": {"provider": "cohere"}})


def test_unsaved_choices_are_tried_without_touching_the_saved_ones(monkeypatch):
    use(monkeypatch, base_cfg(), {"chat": {"provider": "openai", "model": "saved"}})
    tried = registry.effective_config({"chat": {"provider": "openai", "model": "tried"}})
    assert tried.chat.model == "tried"
    assert registry.effective_config().chat.model == "saved"


def test_a_key_is_needed_only_for_the_providers_chosen():
    data = {
        "chat": {"provider": "anthropic", "model": "x"},
        "rerank": {"provider": "cohere", "model": None},
    }
    assert _needed_keys(data) == {"anthropic", "cohere"}
    assert _needed_keys({"rerank": {"provider": "local"}}) == set()
    assert _needed_keys({"chat": {"provider": "ollama", "model": "x"}}) == set()


def test_the_settings_body_rejects_an_unknown_provider():
    with pytest.raises(ValidationError):
        SettingsIn(chat={"provider": "mystery", "model": "x"})
    with pytest.raises(ValidationError):
        SettingsIn(keys={"mystery": "k"})


def test_a_null_key_means_remove_it():
    body = SettingsIn(keys={"openai": None})
    assert body.model_dump(exclude_unset=True)["keys"] == {"openai": None}


def sql(as_of):
    import uuid

    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.models import Chunk

    q = _scope(select(Chunk.id), uuid.uuid4(), None, as_of)
    return str(q.compile(dialect=postgresql.dialect()))


def test_search_without_a_date_covers_only_ready_versions():
    text = sql(None)
    assert "document_version.status =" in text
    assert "effective_from" not in text


def test_search_with_a_date_covers_the_versions_in_effect_that_day():
    text = sql(date(2025, 1, 1))
    assert "document_version.status IN" in text
    assert "effective_from <=" in text
    assert "effective_to >" in text
