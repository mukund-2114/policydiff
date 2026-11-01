import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from pydantic import ValidationError

from app.pipeline.judge import (
    Clause,
    JudgeOutput,
    build_messages,
    final_confidence,
    judge_pair,
    numbers_differ,
    quote_is_real,
    quotes_verified,
)
from app.providers.base import ProviderError, Response

A = Clause(
    "EXP-001", "1.0", None, "5. Claims", "5.1 Expense claims must be submitted within 30 days."
)
B = Clause(
    "TRV-001", "1.0", None, "5. Expense claims", "5.1 Travel claims must be filed within 60 days."
)


def answer(**changes):
    data = dict(
        verdict="conflict",
        type="numeric_mismatch",
        quote_a="must be submitted within 30 days",
        quote_b="must be filed within 60 days",
        explanation="30 days against 60 days.",
        confidence=0.9,
        suggested_owner="Finance",
    )
    return JudgeOutput(**{**data, **changes})


class Chat:
    """A chat model that returns the given replies in turn. A reply of None means no answer."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def generate(self, messages, schema=None):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Response("", reply, 10, 5)


# the prompt


def test_prompt_holds_both_clauses_and_marks_them_as_data():
    system, user = build_messages(A, B)
    assert "untrusted" in system.content
    assert '<clause_a document="EXP-001" version="1.0">' in user.content
    assert "within 60 days" in user.content and "Section: 5. Expense claims" in user.content


def test_prompt_shows_the_effective_date_when_there_is_one():
    from datetime import date

    a = Clause("EXP-001", "2.0", date(2026, 3, 1), None, "text")
    assert "effective 2026-03-01" in build_messages(a, B)[1].content
    assert "Section: none" in build_messages(a, B)[1].content


# the retry


def test_judge_returns_the_first_good_answer_and_counts_tokens():
    chat = Chat(answer())
    out, tokens = judge_pair(chat, A, B)
    assert out.verdict == "conflict" and tokens == 15 and chat.calls == 1


def test_judge_retries_once_when_there_is_no_answer():
    chat = Chat(None, answer())
    out, tokens = judge_pair(chat, A, B)
    assert out.verdict == "conflict" and chat.calls == 2 and tokens == 30


def test_judge_retries_once_when_the_answer_does_not_fit_the_schema():
    try:
        JudgeOutput(verdict="maybe")
    except ValidationError as bad:
        chat = Chat(bad, answer())
    assert judge_pair(chat, A, B)[0].verdict == "conflict"


def test_judge_gives_up_after_two_bad_answers():
    chat = Chat(None, None)
    with pytest.raises(ProviderError):
        judge_pair(chat, A, B)
    assert chat.calls == 2


def test_judge_does_not_swallow_a_provider_error():
    with pytest.raises(ProviderError):
        judge_pair(Chat(ProviderError("no key")), A, B)


# quote verification


def test_a_quote_that_is_in_the_clause_is_real():
    assert quote_is_real("must be submitted within 30 days", A.text)


def test_quotes_ignore_case_spacing_and_curly_quotes():
    assert quote_is_real("MUST  be\nsubmitted", A.text)
    assert quote_is_real("employee’s claim", "The employee's claim is due.")


def test_a_table_row_quote_matches_the_table_text():
    table = "| Payment method | Processing time |\n| --- | --- |\n| Credit card | 7 business days |"
    assert quote_is_real("Credit card | 7 business days", table)


def test_an_invented_or_empty_quote_is_not_real():
    assert not quote_is_real("must be submitted within 45 days", A.text)
    assert not quote_is_real("", A.text)
    assert not quote_is_real("   ", A.text)


def test_both_quotes_must_be_real_in_their_own_clause():
    out = answer()
    assert quotes_verified(out, A.text, B.text)
    assert not quotes_verified(out, B.text, A.text)  # right quotes, swapped clauses
    assert not quotes_verified(answer(quote_b="made up"), A.text, B.text)


# confidence


def test_numbers_differ_only_when_both_have_numbers_that_disagree():
    assert numbers_differ("within 30 days", "within 60 days")
    assert not numbers_differ("within 30 days", "within 30 calendar days")
    assert not numbers_differ("must be approved", "within 60 days")  # no numbers on one side
    assert numbers_differ("CAD 2,500", "CAD 5,000")


def test_confidence_blends_judge_rerank_and_numbers():
    assert final_confidence(1.0, 1.0, True) == 1.0
    assert final_confidence(0.9, 0.5, False) == pytest.approx(0.685)
    assert final_confidence(0.9, 0.5, True) > final_confidence(0.9, 0.5, False)


def test_confidence_stays_between_zero_and_one():
    assert final_confidence(7.0, 3.0, True) == 1.0
    assert final_confidence(-1.0, -1.0, False) == 0.0
