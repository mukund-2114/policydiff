"""Stage 4 helpers: what text goes to the embedding model for a chunk.

The embedding sees the context line first, then the chunk. A bare sentence like "must be submitted
within 30 days" means little alone. With "Expense Policy, version 3.1. Section: 5. Claims" in front,
the vector knows which rule it is. The keyword index (tsvector) is built from the same text, so a
search by words and a search by meaning both see the same thing.

Once table summaries exist (S11), the summary replaces the raw table text here. The raw text stays
on the chunk for the judge and for quote checks.
"""

MAX_CHARS = 24_000  # about 6,000 tokens: under the model limit of 8,191


def embedding_input(context_header: str | None, text: str, summary: str | None = None) -> str:
    body = summary or text
    full = f"{context_header}\n{body}" if context_header else body
    return full[:MAX_CHARS]
