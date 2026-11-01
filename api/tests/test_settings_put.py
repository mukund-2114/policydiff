import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.providers import registry
from app.providers.registry import ChatCfg, EgressCfg, EmbedCfg, ModelsConfig
from app.routers.settings import SettingsIn, put_settings
from app.services import runtime


class Row:
    def __init__(self):
        self.data, self.secrets, self.updated_by = {}, {}, None


class FakeDb:
    """Just enough of a session for put_settings: one settings row, nothing is really stored."""

    def __init__(self, row):
        self.row, self.committed = row, False

    def scalars(self, _query):
        return SimpleNamespace(first=lambda: self.row)

    def scalar(self, _query):
        return 0

    def add(self, _obj):
        pass

    def flush(self):
        pass

    def commit(self):
        self.committed = True


class Embedder:
    def __init__(self, cfg, vector_size=1536):
        self.model, self.dims, self.size = cfg.embed.model, cfg.embed.dims, vector_size
        self.cfg = cfg

    def embed(self, texts):
        return [[0.0] * self.size for _ in texts]


@pytest.fixture
def setup(monkeypatch):
    cfg = ModelsConfig(
        chat=ChatCfg(provider="openai", model="m1"),
        embed=EmbedCfg(provider="openai", model="text-embedding-3-small", dims=1536),
        egress=EgressCfg(allow_cloud=True),
    )
    monkeypatch.setattr(registry, "load_config", lambda: cfg)
    monkeypatch.setattr(runtime, "_row", lambda: None)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")
    probed = []

    def build(c=None):
        probed.append(c.embed.model if c else None)
        return Embedder(c, vector_size=build.size)

    build.size = 1536
    monkeypatch.setattr(registry, "get_embedder", build)
    user = SimpleNamespace(id=uuid.uuid4(), workspace_id=uuid.uuid4())
    return Row(), user, probed, build


def put(row, user, **body):
    return put_settings(SettingsIn(**body), user, FakeDb(row))


def test_the_embedding_probe_tests_the_new_model_not_the_saved_one(setup):
    row, user, probed, _ = setup
    row.data = {"embed": {"provider": "openai", "model": "an-old-choice"}}
    put(row, user, embed={"provider": "openai", "model": "text-embedding-3-large"})
    assert probed == ["text-embedding-3-large"]
    assert row.data["embed"]["model"] == "text-embedding-3-large"


def test_a_model_that_cannot_be_reached_is_refused_and_nothing_is_saved(setup, monkeypatch):
    row, user, _, _ = setup

    def down(c=None):
        raise RuntimeError("no route to host")

    monkeypatch.setattr(registry, "get_embedder", down)
    with pytest.raises(HTTPException) as e:
        put(row, user, embed={"provider": "ollama", "model": "bge-m3"})
    assert e.value.status_code == 400 and "did not answer" in e.value.detail
    assert row.data == {}  # the bad choice was not stored


def test_a_model_with_the_wrong_vector_size_is_refused(setup):
    row, user, _, build = setup
    build.size = 1024
    with pytest.raises(HTTPException) as e:
        put(row, user, embed={"provider": "openai", "model": "some-1024-model"})
    assert "1024" in e.value.detail and "1536" in e.value.detail
    assert row.data == {}


def test_saving_something_else_does_not_probe_the_embedder(setup):
    row, user, probed, _ = setup
    put(row, user, pipeline={"rrf_k": 40})
    assert probed == []
