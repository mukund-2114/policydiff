import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type AskResult } from "../api";
import { field, panel, primary } from "../ui";

// Ask a question about the policies. The answer cites numbered passages, and any open finding that
// involves a cited passage is listed under it. With an "as of" date the search covers the versions
// that were in effect that day, so you can ask what the rule was last March.

const TYPE = {
  numeric_mismatch: "Numbers differ",
  obligation_conflict: "Obligations conflict",
  scope_overlap: "Scope overlap",
  definition_mismatch: "Definitions differ",
  outdated_reference: "Outdated reference",
} as Record<string, string>;

function Result({ r, asOf }: { r: AskResult; asOf: string }) {
  return (
    <div className="space-y-4">
      <section className={`${panel} space-y-2 p-4`}>
        <h2 className="font-medium">Answer{asOf ? ` as of ${asOf}` : ""}</h2>
        <p className="whitespace-pre-wrap">{r.answer}</p>
      </section>

      {r.findings.length > 0 && (
        <section className={`${panel} space-y-2 p-4`}>
          <h2 className="font-medium">
            {r.findings.length} finding{r.findings.length === 1 ? "" : "s"} on these passages
          </h2>
          <ul className="divide-y divide-border">
            {r.findings.map((f) => (
              <li key={f.id} className="py-2">
                <p>
                  <span className="font-medium">{TYPE[f.type] ?? f.type}</span>
                  <span className="ml-2 text-muted">
                    {f.between}, {f.status}, confidence {(f.confidence * 100).toFixed(0)}%
                  </span>
                </p>
                <p>{f.explanation}</p>
              </li>
            ))}
          </ul>
          <a className="text-accent hover:underline" href="#/findings">
            Open the review queue
          </a>
        </section>
      )}

      {r.passages.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium">Passages</h2>
          <ol className="space-y-2">
            {r.passages.map((p) => (
              <li key={p.n} className={`${panel} px-4 py-3 ${p.cited ? "" : "opacity-70"}`}>
                <p className="text-muted">
                  <span className="font-mono">[{p.n}]</span>{" "}
                  <a className="text-accent hover:underline" href={`#/documents/${p.version_id}`}>
                    {p.title} v{p.version_label}
                  </a>
                  , {p.heading_path}
                  {p.page ? `, page ${p.page}` : ""}
                  {p.cited ? "" : ", not cited"}
                </p>
                <p className="mt-1 whitespace-pre-wrap">{p.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

export function Ask() {
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("");
  const ask = useMutation({ mutationFn: () => api.ask(question.trim(), asOf || null) });

  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">Ask</h1>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 3) ask.mutate();
        }}
      >
        <label className="min-w-64 flex-1 space-y-1">
          <span className="text-muted">Question</span>
          <input
            className={field}
            placeholder="For example: how long do I have to submit an expense claim?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-muted">As of (optional)</span>
          <input className={`${field} w-44`} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <button className={primary} disabled={ask.isPending || question.trim().length < 3}>
          {ask.isPending ? "Asking" : "Ask"}
        </button>
      </form>
      <p className="text-muted">
        With a date, the search covers the versions in effect that day. A version with no effective date counts as always
        in effect.
      </p>
      {ask.isError && <p className="text-danger">{(ask.error as Error).message}</p>}
      {ask.data && <Result r={ask.data} asOf={asOf} />}
    </div>
  );
}
