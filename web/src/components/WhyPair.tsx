import type { Finding, FindingSide } from "../api";
import { panel } from "../ui";

// "Why this pair": how the two chunks were matched and how the confidence was built, so a reviewer
// can tell a strong finding from a weak one without opening the pipeline. Every number here is read
// from what the scan stored for the pair. Nothing is recomputed.

const KIND = { text: "Text clause", table: "Table", figure: "Figure" };

function rank(n: unknown, what: string) {
  return typeof n === "number" ? `${what} result ${n}` : `not in the ${what} results`;
}

function Facts({ label, side }: { label: string; side: FindingSide }) {
  return (
    <div className="min-w-0 space-y-1">
      <p className="text-muted">
        {label}: {KIND[side.kind]}
      </p>
      {side.summary && <p>Searched as: {side.summary}</p>}
      {side.facts.length > 0 ? (
        <ul className="font-mono">
          {side.facts.map((f, i) => (
            <li key={i} className="truncate">
              {f.subject}: {f.value}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">No facts were extracted.</p>
      )}
    </div>
  );
}

export function WhyPair({ f }: { f: Finding }) {
  const s = f.scores;
  const rerank = typeof s.rerank === "number" ? s.rerank : 0;
  const judge = typeof s.judge_confidence === "number" ? s.judge_confidence : 0;
  const rows: [string, string][] = [
    ["Found by meaning", rank(s.vector_rank, "vector")],
    ["Found by words", rank(s.keyword_rank, "keyword")],
    ["Reranker score", `${rerank.toFixed(2)} (the pair was kept above 0.50)`],
    ["Judge confidence", `${(judge * 100).toFixed(0)}%`],
    ["Numbers in the quotes", s.numbers_differ ? "They differ" : "Not compared, or the same"],
    ["Quotes found in the text", s.quotes_verified ? "Both" : "No"],
  ];
  return (
    <details className={`${panel} p-4`}>
      <summary className="cursor-pointer font-medium">Why this pair</summary>
      <div className="mt-3 space-y-3">
        <dl className="grid grid-cols-[12rem_1fr] gap-y-1">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="font-mono">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="text-muted">
          Confidence is 65% judge, 20% reranker score and 15% for differing numbers: {(f.confidence * 100).toFixed(0)}%
          here. Prompt {String(s.prompt_version ?? "unknown")}.
        </p>
        <div className="grid gap-3 border-t border-border pt-3 md:grid-cols-2">
          <Facts label="A" side={f.a} />
          <Facts label="B" side={f.b} />
        </div>
      </div>
    </details>
  );
}
