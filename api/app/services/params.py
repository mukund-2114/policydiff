"""The search and ranking numbers an admin can change (D53, D54).

Every number is defined once, in `PARAMS`: its default, its allowed range, what raising or lowering
it does, and whether it changes the cost. The Settings page is drawn from this list, the API checks
input against it, and the search code reads the values through `get_params()`. Adding a number later
is one more line here and one more field on `PipelineParams`.

The values live in the settings row (`data["pipeline"]`). Reading is forgiving on purpose: a stored
value that is missing, of the wrong type or out of range falls back to its default, so a bad value
can never stop a scan. Writing is strict, so the page tells the admin what is wrong.
"""

# ruff: noqa: E501  (the descriptions are sentences for admins, not code)
from dataclasses import dataclass

from app.services import runtime


@dataclass(frozen=True)
class PipelineParams:
    """The values the pipeline runs with. The defaults here are the tuned ones (D39, D41)."""

    vector_results: int = 25  # nearest chunks by meaning, per search
    keyword_results: int = 25  # best chunks by words, per search; 0 turns keyword search off
    bm25_k1: float = 1.2  # how much repeating a word keeps helping
    bm25_b: float = 0.75  # how much a long chunk is marked down
    scan_rewrites: int = 0  # multi-query rewrites per clause in a scan
    ask_rewrites: int = 3  # multi-query rewrites per question in Ask
    rrf_k: int = 60
    fused_keep: int = 30  # kept after merging the two lists
    rerank_threshold: float = 0.5
    max_candidates: int = 8
    mmr_lambda: float = 0.8
    final_candidates: int = 5
    chunk_strategy: str = "structure"  # how a clause over the size limit is split
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50

    def funnel(self) -> dict:
        """The keyword arguments `apply_funnel` takes."""
        return {
            "threshold": self.rerank_threshold,
            "max_reranked": self.max_candidates,
            "keep": self.final_candidates,
            "lam": self.mmr_lambda,
        }


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    group: str
    low: float
    high: float
    step: float
    more: str  # what happens when it goes up
    less: str  # what happens when it goes down
    cost: str | None = None  # set when changing it changes the cost
    cost_up: bool = True  # true: a higher value costs more; false: a lower value costs more
    options: tuple[str, ...] | None = None  # a choice from a list, not a number
    unlock: str | None = None  # what has to be done before a change takes effect

    @property
    def default(self):
        return getattr(PipelineParams(), self.key)

    @property
    def is_int(self) -> bool:
        return isinstance(self.default, int)

    @property
    def is_choice(self) -> bool:
        return self.options is not None


PARAMS = [
    Param(
        "vector_results",
        "Matches by meaning",
        "Search",
        5,
        100,
        1,
        more="Finds more clauses that say the same thing in different words. The reranker has more to score.",
        less="Faster, but a clause worded very differently may be missed.",
        cost="Costs more only if the reranker is Cohere or the chat model, because each extra match is scored.",
    ),
    Param(
        "keyword_results",
        "Matches by words",
        "Search",
        0,
        100,
        1,
        more="Finds more clauses that share exact words, such as a form name or a number.",
        less="Relies more on meaning. At 0 the keyword search is switched off.",
        cost="Costs more only if the reranker is Cohere or the chat model.",
    ),
    Param(
        "bm25_k1",
        "Word repeats (BM25 k1)",
        "Search",
        0,
        3,
        0.1,
        more="A word repeated many times in a clause keeps adding to its score.",
        less="Seeing a word once counts nearly as much as seeing it often.",
    ),
    Param(
        "bm25_b",
        "Clause length (BM25 b)",
        "Search",
        0,
        1,
        0.05,
        more="A long clause is marked down more, so short, focused clauses win on a word match.",
        less="Length matters less. At 0 a long clause is not marked down at all.",
    ),
    Param(
        "ask_rewrites",
        "Extra wordings per question",
        "Multi-query",
        0,
        5,
        1,
        more="Each question is also searched in other words, so a policy that phrases things differently is still found. One more model call per question.",
        less="Only the question as written is searched. At 0 there is no extra call.",
        cost="Each extra wording adds a search and a little model time. It adds one model call in total, plus one embedding call.",
    ),
    Param(
        "scan_rewrites",
        "Extra wordings per clause in a scan",
        "Multi-query",
        0,
        5,
        1,
        more="Every clause is also searched in other words, so a conflict worded very differently from its partner is still found. Best recall, but a scan makes one more model call and one more embedding call for every clause.",
        less="Only the clause as written is searched. At 0 a scan costs what it did before.",
        cost="Adds a model call and an embedding call for every clause scanned, and more candidates reach the judge. Run Preview to see the effect before a full scan.",
    ),
    Param(
        "rrf_k",
        "Rank blending",
        "Search",
        10,
        100,
        1,
        more="The two searches count more equally. A clause that is first in one list gets less of a lead.",
        less="The top places of each list count for more, so one strong match wins over agreement.",
    ),
    Param(
        "fused_keep",
        "Kept after blending",
        "Search",
        10,
        100,
        1,
        more="More clauses go on to the reranker, so fewer related clauses are lost early.",
        less="Faster, but a related clause ranked low by both searches is dropped before it is scored.",
        cost="Costs more only if the reranker is Cohere or the chat model.",
    ),
    Param(
        "rerank_threshold",
        "Relatedness cut-off",
        "Ranking",
        0,
        1,
        0.05,
        more="Only clauses that are clearly about the same thing are judged. Fewer judge calls, a little more risk of a miss.",
        less="More clauses are judged, including loosely related ones. Fewer misses, more judge calls and more false alarms.",
        cost="Lowering it sends more pairs to the judge, which costs more.",
        cost_up=False,
    ),
    Param(
        "max_candidates",
        "Most candidates per clause",
        "Ranking",
        1,
        20,
        1,
        more="More related clauses are considered before near-copies are removed.",
        less="Only the best few are considered, so a true partner ranked low can be lost.",
        cost="Raising it only costs more if the final number below is also raised.",
    ),
    Param(
        "mmr_lambda",
        "Relevance against variety",
        "Ranking",
        0,
        1,
        0.05,
        more="Favours the most relevant clauses, even if they repeat each other.",
        less="Pushes for variety: a clause that repeats one already chosen is dropped for a different one. Too low can drop a true partner.",
    ),
    Param(
        "final_candidates",
        "Clauses judged per clause",
        "Ranking",
        1,
        10,
        1,
        more="Each clause is compared with more others. Fewer misses.",
        less="Fewer comparisons. Faster, but a conflict with a lower-ranked clause is missed.",
        cost="Each extra clause is one more judge call for every clause scanned, so cost rises in step.",
    ),
]

PARAMS += [
    Param(
        "chunk_strategy",
        "How long clauses are split",
        "Chunking",
        0,
        0,
        0,
        more="structure: a clause is one chunk. One over the size limit is cut at sentence ends with a little repeated text, so no sentence loses its context.",
        less="semantic: a clause over the size limit is cut where its topic shifts, found by comparing sentences by meaning. Pieces follow the ideas, not a size. It makes one embedding call per long clause.",
        cost="Semantic splitting embeds the sentences of each long clause, a small extra cost per document.",
        options=("structure", "semantic"),
        unlock="Applies to a document when it is cut again.",
    ),
    Param(
        "chunk_max_tokens",
        "Largest chunk (tokens)",
        "Chunking",
        150,
        1000,
        25,
        more="Fewer, longer chunks. A finding then covers a bigger passage, and fewer clauses are split.",
        less="More, shorter chunks. Findings point at smaller passages, but each scan makes more comparisons.",
        cost="Smaller chunks mean more chunks, so more judge calls in a scan.",
        cost_up=False,
        unlock="Applies to a document when it is cut again.",
    ),
    Param(
        "chunk_overlap_tokens",
        "Repeated text between pieces (tokens)",
        "Chunking",
        0,
        150,
        10,
        more="More of the end of one piece is repeated at the start of the next, so a split sentence keeps its context.",
        less="Less repetition and fewer tokens. At 0 a piece starts cold. Not used by the semantic strategy.",
        unlock="Applies to a document when it is cut again.",
    ),
]

BY_KEY = {p.key: p for p in PARAMS}


def clean(raw: dict, strict: bool = False) -> dict:
    """Keep the valid values of `raw`. With `strict`, a bad or unknown one raises ValueError."""
    out = {}
    for key, value in raw.items():
        p = BY_KEY.get(key)
        if p is None:
            if strict:
                raise ValueError(f"Unknown setting: {key}")
            continue
        if p.is_choice:
            if value in p.options:
                out[key] = value
            elif strict:
                raise ValueError(f"{p.label} must be one of: {', '.join(p.options)}.")
            continue
        ok = isinstance(value, int | float) and not isinstance(value, bool)
        ok = ok and p.low <= value <= p.high
        if ok and p.is_int:
            ok = float(value).is_integer()
        if ok:
            out[key] = int(value) if p.is_int else round(float(value), 4)
        elif strict:
            raise ValueError(f"{p.label} must be between {p.low:g} and {p.high:g}.")
    return out


def get_params(data: dict | None = None) -> PipelineParams:
    """The values in use now. Pass `data` to try unsaved values, as the Preview button does."""
    data = runtime.stored_data() if data is None else data
    stored = data.get("pipeline")
    return PipelineParams(**clean(stored if isinstance(stored, dict) else {}))


def describe(params: PipelineParams) -> list[dict]:
    """What the Settings page needs to draw one row per number."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "group": p.group,
            "low": p.low,
            "high": p.high,
            "step": p.step,
            "default": p.default,
            "value": getattr(params, p.key),
            "more": p.more,
            "less": p.less,
            "cost": p.cost,
            "cost_up": p.cost_up,
            "options": list(p.options) if p.options else None,
            "unlock": p.unlock,
        }
        for p in PARAMS
    ]
