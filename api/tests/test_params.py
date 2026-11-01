import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import dataclasses

import pytest

from app.retrieval import funnel
from app.retrieval.search import keyword_search
from app.routers.settings import Choices
from app.services import params


def test_every_number_on_the_page_is_a_field_and_every_field_is_on_the_page():
    fields = {f.name for f in dataclasses.fields(params.PipelineParams)}
    assert fields == set(params.BY_KEY)


def test_every_number_explains_what_raising_and_lowering_it_does():
    for p in params.PARAMS:
        assert p.more and p.less, p.key
        if p.is_choice:
            assert p.default in p.options, p.key
        else:
            assert p.low <= p.default <= p.high, p.key
        assert "—" not in p.more + p.less + (p.cost or "")  # the style guide bans em dashes


def test_the_funnel_defaults_are_the_parameter_defaults():
    d = params.PipelineParams()
    assert funnel.RELATED_THRESHOLD == d.rerank_threshold
    assert funnel.MAX_RERANKED == d.max_candidates
    assert funnel.MMR_LAMBDA == d.mmr_lambda
    assert funnel.MMR_KEEP == d.final_candidates


def test_funnel_arguments_follow_the_values():
    p = params.PipelineParams(rerank_threshold=0.3, max_candidates=4, final_candidates=2)
    assert p.funnel() == {"threshold": 0.3, "max_reranked": 4, "keep": 2, "lam": 0.8}


def test_nothing_saved_gives_the_defaults():
    assert params.get_params({}) == params.PipelineParams()
    assert params.get_params({"pipeline": None}) == params.PipelineParams()


def test_saved_values_are_used():
    got = params.get_params({"pipeline": {"rrf_k": 40, "mmr_lambda": 0.6}})
    assert (got.rrf_k, got.mmr_lambda) == (40, 0.6)
    assert got.vector_results == 25  # untouched ones keep their default


def test_a_bad_stored_value_falls_back_to_its_default_and_keeps_the_good_ones():
    stored = {
        "pipeline": {
            "rrf_k": 5,  # below the range
            "fused_keep": "lots",  # wrong type
            "final_candidates": 2.5,  # a count must be whole
            "mmr_lambda": True,  # a bool is not a number here
            "nonsense": 1,  # unknown
            "vector_results": 50,  # fine
        }
    }
    got = params.get_params(stored)
    default = params.PipelineParams()
    assert got.rrf_k == default.rrf_k
    assert got.fused_keep == default.fused_keep
    assert got.final_candidates == default.final_candidates
    assert got.mmr_lambda == default.mmr_lambda
    assert got.vector_results == 50


def test_a_stored_value_that_is_not_a_dict_is_ignored():
    assert params.get_params({"pipeline": [1, 2]}) == params.PipelineParams()


def test_saving_a_bad_value_is_refused_with_a_reason():
    with pytest.raises(ValueError, match="Rank blending must be between 10 and 100"):
        params.clean({"rrf_k": 5}, strict=True)
    with pytest.raises(ValueError, match="Unknown setting"):
        params.clean({"nonsense": 1}, strict=True)


def test_whole_numbers_stay_whole_and_decimals_stay_decimals():
    out = params.clean({"vector_results": 30.0, "rerank_threshold": 1}, strict=True)
    assert out == {"vector_results": 30, "rerank_threshold": 1.0}
    assert isinstance(out["vector_results"], int)


def test_zero_keyword_results_switches_keyword_search_off():
    assert keyword_search(None, None, "expense claim deadline", limit=0) == []


def test_the_page_describes_each_number_with_its_current_value():
    rows = params.describe(params.PipelineParams(rrf_k=40))
    row = next(r for r in rows if r["key"] == "rrf_k")
    assert (row["value"], row["default"]) == (40, 60)
    assert len(rows) == len(params.PARAMS)


def test_a_choice_must_be_one_of_the_listed_options():
    assert params.clean({"chunk_strategy": "semantic"}, strict=True) == {
        "chunk_strategy": "semantic"
    }
    with pytest.raises(ValueError, match="must be one of: structure, semantic"):
        params.clean({"chunk_strategy": "magic"}, strict=True)
    # read side: a stored bad choice falls back to the default
    assert params.get_params({"pipeline": {"chunk_strategy": 7}}).chunk_strategy == "structure"


def test_the_chunking_numbers_are_on_the_page_with_a_note_on_when_they_apply():
    rows = {r["key"]: r for r in params.describe(params.PipelineParams())}
    assert {"chunk_strategy", "chunk_max_tokens", "chunk_overlap_tokens"} <= set(rows)
    assert rows["chunk_strategy"]["options"] == ["structure", "semantic"]
    assert "cut again" in rows["chunk_max_tokens"]["unlock"]


def test_the_settings_body_takes_the_numbers():
    assert Choices(pipeline={"rrf_k": 40}).pipeline == {"rrf_k": 40}
