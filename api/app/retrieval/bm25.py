"""BM25, written by hand (D4): scores how well a chunk matches the words of a query.

It replaces Postgres's own `ts_rank_cd` for the keyword half of the search. Two ideas make it work:
  - a rare word counts for more than a common one (idf: a form name beats the word "the"), and
  - repeating a word helps less each time, and a long chunk is not favoured just for being long
    (term frequency, saturated by k1, and length normalised by b).

Postgres still does the first cut: it finds the chunks that match any query word with its keyword
index. BM25 then re-scores that pool. The word counts come from the stored `tsvector` itself (it
holds each stemmed word and its positions), so the query and the chunks are stemmed the same way.
The pure functions at the top are tested without a database. The two small functions at the bottom
read the statistics (how many chunks, their average length, how many chunks hold each word).
"""

import math
import re
import uuid
from collections.abc import Hashable
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

POOL = 200  # chunks Postgres hands to BM25 to re-score

# One entry of a tsvector as text: 'word':3,9 (positions, optionally with a weight letter).
_ENTRY = re.compile(r"'((?:[^']|'')+)':([0-9A-D,]+)")


@dataclass
class Stats:
    """What BM25 needs to know about the whole library."""

    n_docs: int = 0
    avg_len: float = 0.0
    doc_freq: dict[str, int] = field(default_factory=dict)  # word -> chunks that hold it


def parse_tsvector(value: str) -> dict[str, int]:
    """Word counts from a tsvector written as text: "'claim':3,8 'day':5" gives claim 2, day 1."""
    return {
        m.group(1).replace("''", "'"): len(m.group(2).split(",")) for m in _ENTRY.finditer(value)
    }


def idf(word: str, stats: Stats) -> float:
    """How rare the word is. Always above zero, so a very common word never scores negative."""
    df = stats.doc_freq.get(word, 0)
    return math.log(1 + (stats.n_docs - df + 0.5) / (df + 0.5))


def score(terms: list[str], counts: dict[str, int], stats: Stats, k1: float, b: float) -> float:
    """The BM25 score of one chunk (its word counts) for the query words."""
    length = sum(counts.values())
    norm = 1 - b + b * (length / stats.avg_len) if stats.avg_len else 1.0
    total = 0.0
    for word in set(terms):
        tf = counts.get(word, 0)
        if tf:
            total += idf(word, stats) * tf * (k1 + 1) / (tf + k1 * norm)
    return total


def rank(
    terms: list[str],
    pool: dict[Hashable, dict[str, int]],
    stats: Stats,
    k1: float = 1.2,
    b: float = 0.75,
    limit: int = 25,
) -> list[Hashable]:
    """Chunk ids best first. A chunk matching no query word is left out."""
    scored = [(score(terms, counts, stats, k1, b), key) for key, counts in pool.items()]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: -s[0])  # stable, so ties keep the order Postgres gave
    return [key for _, key in scored[:limit]]


def load_stats(db: Session, workspace_id: uuid.UUID) -> Stats:
    """Count the library's words with Postgres's `ts_stat`. Done once per scan or question."""
    # The id is a UUID, so it cannot carry SQL; ts_stat wants the query as a string.
    ws = uuid.UUID(str(workspace_id))
    inner = f"SELECT tsv FROM chunk WHERE workspace_id = '{ws}' AND tsv IS NOT NULL"
    rows = db.execute(text("SELECT word, ndoc, nentry FROM ts_stat(:q)"), {"q": inner}).all()
    n_docs = db.scalar(
        text("SELECT count(*) FROM chunk WHERE workspace_id = :w AND tsv IS NOT NULL"),
        {"w": workspace_id},
    )
    words = sum(r.nentry for r in rows)
    return Stats(
        n_docs=n_docs or 0,
        avg_len=words / n_docs if n_docs else 0.0,
        doc_freq={r.word: r.ndoc for r in rows},
    )


def query_terms(db: Session, query_text: str) -> list[str]:
    """The query's words the way Postgres stems them (so "claims" meets "claim")."""
    return list(
        db.scalar(text("SELECT tsvector_to_array(to_tsvector('english', :q))"), {"q": query_text})
        or []
    )
