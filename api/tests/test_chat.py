import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.providers.base import Message, ProviderError, Response, stream_chat
from app.services.ask import (
    SearchPlan,
    build_messages,
    cited_numbers,
    plain_pieces,
    plan_search,
    search_text,
)

HISTORY = [
    {"role": "user", "content": "How long do I have to submit an expense claim?"},
    {"role": "assistant", "content": "30 days [1]."},
]
PASSAGE = {
    "n": 1,
    "title": "EXP-001",
    "version_label": "1.0",
    "heading_path": "5. Claims",
    "text": "Claims within 30 days.",
}


def test_a_short_follow_up_is_searched_with_the_question_before_it():
    assert search_text("and for contractors?", HISTORY).startswith("How long do I have")
    assert search_text("and for contractors?", HISTORY).endswith("and for contractors?")


def test_a_long_question_or_a_first_message_is_searched_as_it_is():
    long_q = "What is the maximum amount an employee may claim for a hotel night in Toronto?"
    assert search_text(long_q, HISTORY) == long_q
    assert search_text("hi", []) == "hi"


def test_citations_are_listed_once_in_order_and_out_of_range_ones_are_dropped():
    assert cited_numbers("A [2] and B [1], again [2], and [9].", 3) == [2, 1]
    assert cited_numbers("No citations here.", 3) == []


def test_the_model_sees_earlier_turns_then_the_passages_and_the_message():
    msgs = build_messages("and for contractors?", HISTORY, [PASSAGE])
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]
    last = msgs[-1].content
    assert '<passage n="1" document="EXP-001"' in last
    assert last.endswith("Message: and for contractors?")


def test_with_no_passages_the_model_is_told_nothing_matched():
    last = build_messages("hello", [], [])[-1].content
    assert "No policy passages matched" in last


def test_a_model_that_cannot_stream_still_gives_text_then_usage():
    class Plain:
        def generate(self, messages, schema=None):
            return Response("hello there", None, 7, 3)

    assert list(stream_chat(Plain(), [Message("user", "hi")])) == [
        ("text", "hello there"),
        ("usage", 10),
    ]


def test_a_model_that_streams_is_used_directly():
    class Streams:
        def stream(self, messages):
            yield "text", "a"
            yield "text", "b"
            yield "usage", 5

    assert list(stream_chat(Streams(), [])) == [("text", "a"), ("text", "b"), ("usage", 5)]


def test_a_citation_with_the_document_name_inside_still_counts():
    assert cited_numbers("Sixty days [TRV-001, 1]. Thirty [EXP-001, 2].", 2) == [1, 2]


def test_the_em_dash_becomes_a_comma_even_when_it_arrives_alone():
    pieces = [("text", "Hi"), ("text", " —"), ("text", " I can"), ("text", " help."), ("usage", 4)]
    out = list(plain_pieces(iter(pieces)))
    assert "".join(v for k, v in out if k == "text") == "Hi, I can help."
    assert out[-1] == ("usage", 4)


class PlanChat:
    def __init__(self, plan=None):
        self.plan, self.sent = plan, None

    def generate(self, messages, schema=None):
        self.sent = messages
        if self.plan is None:
            raise ProviderError("down")
        return Response("", self.plan, 1, 1)


def test_the_model_cleans_a_typo_ridden_message_into_a_search_query():
    plan = SearchPlan(search_query="refund for a cancelled flight", needs_policy_lookup=True)
    chat = PlanChat(plan)
    got = plan_search("can i get a refudn i can th flight", [], chat)
    assert got == plan
    assert "Last message: can i get a refudn" in chat.sent[1].content


def test_the_planner_sees_the_earlier_turns_so_short_replies_make_sense():
    chat = PlanChat(SearchPlan(search_query="x", needs_policy_lookup=True))
    plan_search("refundable", HISTORY, chat)
    assert "How long do I have to submit an expense claim?" in chat.sent[1].content


def test_if_the_planner_fails_the_plain_rules_still_search():
    got = plan_search("and for contractors?", HISTORY, PlanChat(None))
    assert got.needs_policy_lookup is True
    assert got.search_query.startswith("How long do I have")


def test_the_plan_asks_for_other_wordings_only_when_rewrites_are_on():
    plan = SearchPlan(search_query="claim deadline", needs_policy_lookup=True)
    chat = PlanChat(plan)
    plan_search("deadline?", [], chat, rewrites=0)
    assert "always an empty list" in chat.sent[0].content
    plan_search("deadline?", [], chat, rewrites=3)
    asked = chat.sent[0].content
    assert "3 other wordings" in asked
    assert "Never add a number" in asked  # a made-up value would pull in the wrong clauses


def test_other_wordings_are_cleaned_and_cut_to_the_number_asked():
    plan = SearchPlan(
        search_query="claim deadline",
        needs_policy_lookup=True,
        alternatives=["  time  limit to file ", "Claim Deadline", "time limit to file", "a", "b"],
    )
    got = plan_search("deadline?", [], PlanChat(plan), rewrites=2)
    assert got.alternatives == ["time limit to file", "a"]


def test_a_plain_greeting_or_thanks_skips_the_lookup_and_the_model():
    chat = PlanChat(SearchPlan(search_query="x", needs_policy_lookup=True))
    for text in ("hello", "Thanks!", "thank you so much.", "  hi there ", "Good morning", "ok"):
        assert plan_search(text, [], chat).needs_policy_lookup is False, text
    assert chat.sent is None  # the model was never asked


def test_a_message_that_only_starts_like_small_talk_is_still_looked_up():
    chat = PlanChat(SearchPlan(search_query="refund rule", needs_policy_lookup=True))
    for text in (
        "hello, what is the refund rule",
        "ok but how long do claims take",
        "thanks. and for travel?",
    ):
        assert plan_search(text, [], chat).needs_policy_lookup is True, text
