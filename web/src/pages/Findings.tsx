import { useQuery } from "@tanstack/react-query";
import { api, type Finding, type FindingSide } from "../api";
import { panel } from "../ui";

// A plain list of what the scans found, most confident first. The review queue (S9) replaces this
// with filters, keyboard shortcuts and side-by-side PDFs. For now it lets you read each finding and
// check that both quotes really are in the clauses.

const TYPE = {
  numeric_mismatch: "Numbers differ",
  obligation_conflict: "Obligations conflict",
  scope_overlap: "Scope overlap",
  definition_mismatch: "Definitions differ",
  outdated_reference: "Outdated reference",
} as Record<string, string>;

function Side({ label, side, quote }: { label: string; side: FindingSide; quote: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <p className="text-muted">
        {label}: <span className="font-medium text-text">{side.title} v{side.version_label}</span>, {side.heading_path}
        {side.page ? `, page ${side.page}` : ""}
      </p>
      <blockquote className="border-l-2 border-accent pl-3">{quote}</blockquote>
    </div>
  );
}

export function Findings() {
  const findings = useQuery({ queryKey: ["findings"], queryFn: api.findings });
  const rows = findings.data ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">Findings</h1>
      {findings.isSuccess && rows.length === 0 && (
        <p className="text-muted">No findings yet. Open a document and press Scan for conflicts.</p>
      )}
      <ol className="space-y-3">
        {rows.map((f: Finding) => (
          <li key={f.id} className={`${panel} space-y-3 p-4`}>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="font-medium">{TYPE[f.type] ?? f.type}</span>
              <span className="text-muted">confidence {(f.confidence * 100).toFixed(0)}%</span>
              {f.owner && <span className="text-muted">suggested owner {f.owner}</span>}
              <span className="ml-auto text-muted">{f.status}</span>
            </div>
            <p>{f.explanation}</p>
            <div className="grid gap-3 md:grid-cols-2">
              <Side label="A" side={f.a} quote={f.quote_a} />
              <Side label="B" side={f.b} quote={f.quote_b} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
