import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Finding, type FindingSide } from "../api";
import { PdfClause } from "../components/PdfClause";
import { WhyPair } from "../components/WhyPair";
import { button, field, panel, primary } from "../ui";

// The review queue. The list on the left is filtered by status and type, the finding you pick opens
// on the right. Keys: j and k move, c confirms, d dismisses, r marks resolved, o reopens. They are
// ignored while you type in a box, so writing a reason does not dismiss anything.
// Under each quote is the PDF page the clause is on, with the clause marked.

const TYPE = {
  numeric_mismatch: "Numbers differ",
  obligation_conflict: "Obligations conflict",
  scope_overlap: "Scope overlap",
  definition_mismatch: "Definitions differ",
  outdated_reference: "Outdated reference",
} as Record<string, string>;

// Findings below this confidence are hidden until you lower it. The eval in evals/judge_eval.py
// prints precision and recall at each cut-off; DEFAULT_MIN is the one chosen from it.
const DEFAULT_MIN = 0.9;
const MIN_OPTIONS = [0, 0.7, 0.8, 0.9];

const STATUS = ["open", "confirmed", "dismissed", "resolved"];

// key -> the status it sets
const KEYS: Record<string, string> = { c: "confirmed", d: "dismissed", r: "resolved", o: "open" };

function Side({ label, side, quote }: { label: string; side: FindingSide; quote: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <p className="text-muted">
        {label}: <span className="font-medium text-text">{side.title} v{side.version_label}</span>, {side.heading_path}
        {side.page ? `, page ${side.page}` : ""}
      </p>
      <blockquote className="border-l-2 border-accent pl-3">{quote}</blockquote>
      <PdfClause side={side} />
    </div>
  );
}

function Detail({ f, onDecide, busy }: { f: Finding; onDecide: (status: string, note: string) => void; busy: boolean }) {
  const [note, setNote] = useState("");
  const [large, setLarge] = useState(false); // one page per row, so the text is readable
  useEffect(() => setNote(f.resolution_note ?? ""), [f.id, f.resolution_note]);
  return (
    <div className={`${panel} space-y-4 p-4`}>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="font-medium">{TYPE[f.type] ?? f.type}</span>
        <span className="text-muted">confidence {(f.confidence * 100).toFixed(0)}%</span>
        {f.owner && <span className="text-muted">suggested owner {f.owner}</span>}
        <span className="ml-auto text-muted">{f.status}</span>
      </div>
      <p>{f.explanation}</p>
      <WhyPair f={f} />
      <button className={button} onClick={() => setLarge(!large)}>
        {large ? "Show pages side by side" : "Enlarge pages"}
      </button>
      <div className={`grid gap-3 ${large ? "" : "md:grid-cols-2"}`}>
        <Side label="A" side={f.a} quote={f.quote_a} />
        <Side label="B" side={f.b} quote={f.quote_b} />
      </div>
      <input
        className={field}
        placeholder="Reason or note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <button className={primary} disabled={busy} onClick={() => onDecide("confirmed", note)}>
          Confirm (c)
        </button>
        <button className={button} disabled={busy} onClick={() => onDecide("dismissed", note)}>
          Dismiss (d)
        </button>
        <button className={button} disabled={busy} onClick={() => onDecide("resolved", note)}>
          Mark resolved (r)
        </button>
        <button className={button} disabled={busy || f.status === "open"} onClick={() => onDecide("open", note)}>
          Reopen (o)
        </button>
      </div>
    </div>
  );
}

export function Findings() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("open");
  const [type, setType] = useState("");
  const [min, setMin] = useState(DEFAULT_MIN);
  const [index, setIndex] = useState(0);

  const findings = useQuery({ queryKey: ["findings"], queryFn: api.findings });
  const all = findings.data ?? [];
  const matching = all.filter((f) => (!status || f.status === status) && (!type || f.type === type));
  const rows = matching.filter((f) => f.confidence >= min);
  const current: Finding | undefined = rows[Math.min(index, rows.length - 1)];

  const decide = useMutation({
    mutationFn: (v: { id: string; status: string; note: string }) =>
      api.updateFinding(v.id, { status: v.status, resolution_note: v.note || null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["findings"] }),
  });
  const act = (f: Finding, next: string, note = "") => decide.mutate({ id: f.id, status: next, note });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "j") setIndex((i) => Math.min(i + 1, rows.length - 1));
      else if (e.key === "k") setIndex((i) => Math.max(i - 1, 0));
      else if (KEYS[e.key] && current && !decide.isPending) act(current, KEYS[e.key]);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">Findings</h1>
      <div className="flex flex-wrap items-center gap-3">
        <select className={`${field} w-44`} value={status} onChange={(e) => (setStatus(e.target.value), setIndex(0))}>
          <option value="">All statuses</option>
          {STATUS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select className={`${field} w-56`} value={type} onChange={(e) => (setType(e.target.value), setIndex(0))}>
          <option value="">All types</option>
          {Object.entries(TYPE).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select className={`${field} w-48`} value={min} onChange={(e) => (setMin(Number(e.target.value)), setIndex(0))}>
          {MIN_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {m === 0 ? "Any confidence" : `Confidence ${m * 100}% or more`}
            </option>
          ))}
        </select>
        <a
          className={button}
          href={`/api/findings.csv?min_confidence=${min}${status ? `&status=${status}` : ""}${type ? `&type=${type}` : ""}`}
        >
          Export CSV
        </a>
        <p className="text-muted">
          {rows.length} shown
          {matching.length > rows.length ? `, ${matching.length - rows.length} hidden by confidence` : ""}. j and k move,
          c confirms, d dismisses, r resolves.
        </p>
      </div>
      {findings.isSuccess && all.length === 0 && (
        <p className="text-muted">No findings yet. Open a document and press Scan for conflicts.</p>
      )}
      {findings.isSuccess && all.length > 0 && rows.length === 0 && (
        <p className="text-muted">
          Nothing matches these filters. Choose All statuses to see decided findings, or Any confidence to see weaker
          ones.
        </p>
      )}
      {decide.isError && <p className="text-danger">{(decide.error as Error).message}</p>}
      {rows.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
          <ol className={`${panel} max-h-[70vh] divide-y divide-border overflow-y-auto`}>
            {rows.map((f, i) => (
              <li key={f.id}>
                <button
                  className={`block w-full px-3 py-2 text-left hover:bg-bg ${f === current ? "bg-bg" : ""}`}
                  onClick={() => setIndex(i)}
                >
                  <span className="font-medium">{TYPE[f.type] ?? f.type}</span>
                  <span className="ml-2 text-muted">{(f.confidence * 100).toFixed(0)}%</span>
                  <span className="block truncate text-muted">
                    {f.a.title} / {f.b.title}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          {current && <Detail f={current} busy={decide.isPending} onDecide={(s, n) => act(current, s, n)} />}
        </div>
      )}
    </div>
  );
}
