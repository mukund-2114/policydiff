import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ParsedPage, type Stage } from "../api";
import { button, formatDuration, panel, td, th } from "../ui";

// Stages that are planned but not built yet. They are listed so the whole pipeline is visible.
const UPCOMING = [
  ["Chunking", "Cut the text into clauses and keep the heading path of each one."],
  ["Contextual headers", "Add the document title, version and heading path in front of each chunk."],
  ["Embedding and indexing", "Turn each chunk into a vector and a keyword index."],
];

function StageRow({ s }: { s: Stage }) {
  return (
    <li className="space-y-2 border-b border-border px-4 py-3 last:border-0">
      <div className="flex items-baseline gap-3">
        <span className="font-medium capitalize">{s.stage}</span>
        <span className={`font-mono ${s.status === "failed" ? "text-danger" : "text-muted"}`}>{s.status}</span>
        <span className="ml-auto font-mono text-muted">{formatDuration(s.duration_ms)}</span>
      </div>
      {s.detail && (
        <dl className="grid grid-cols-[8rem_1fr] gap-y-0.5 font-mono">
          {Object.entries(s.detail).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
              <dd>{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {s.error && <p className="font-mono text-danger">{s.error}</p>}
    </li>
  );
}

function Pipeline({ id }: { id: string }) {
  const v = useQuery({
    queryKey: ["version", id],
    queryFn: () => api.version(id),
    refetchInterval: (q) => (q.state.data && ["queued", "parsing"].includes(q.state.data.status) ? 1000 : false),
  });
  if (!v.data) return null;
  return (
    <div className="space-y-3">
      <p className="text-muted">
        Status: <span className="font-mono text-text">{v.data.status}</span>
      </p>
      <ol className={panel}>
        <li className="flex items-baseline gap-3 border-b border-border px-4 py-3">
          <span className="font-medium">Upload</span>
          <span className="font-mono text-muted">done</span>
          <span className="ml-auto text-muted">File stored, duplicate check passed</span>
        </li>
        {v.data.stages.map((s) => (
          <StageRow key={s.started_at} s={s} />
        ))}
        {UPCOMING.map(([name, what]) => (
          <li key={name} className="flex items-baseline gap-3 border-t border-border px-4 py-3 text-muted">
            <span className="font-medium">{name}</span>
            <span className="font-mono">not built yet</span>
            <span className="ml-auto text-right">{what}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ParsedView({ id }: { id: string }) {
  const parsed = useQuery({ queryKey: ["parsed", id], queryFn: () => api.parsed(id), retry: false });
  if (parsed.isError) return <p className="text-muted">Nothing to show until the document has been parsed.</p>;
  if (!parsed.data) return null;
  return (
    <div className="space-y-4">
      <p className="text-muted">
        What the parser saw. Font size and bold are how the chunker will tell a heading from a clause.
      </p>
      {parsed.data.pages.map((p: ParsedPage) => (
        <section key={p.number} className={panel}>
          <h3 className="border-b border-border px-4 py-2 font-medium">
            Page {p.number}
            <span className="ml-3 font-mono font-normal text-muted">
              {p.blocks.length} blocks, {p.tables.length} tables, {p.images} images
            </span>
          </h3>
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={`${th} w-16`}>Size</th>
                <th className={`${th} w-14`}>Bold</th>
                <th className={th}>Text</th>
              </tr>
            </thead>
            <tbody>
              {p.blocks.map((b, i) => (
                <tr key={i} className="border-t border-border">
                  <td className={`${td} font-mono`}>{b.size}</td>
                  <td className={`${td} font-mono`}>{b.bold ? "yes" : ""}</td>
                  <td className={`${td} whitespace-pre-wrap`}>{b.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {p.tables.map((t, i) => (
            <div key={i} className="border-t border-border px-4 py-3">
              <p className="mb-2 text-muted">Table found by the parser</p>
              <table className="border-collapse">
                <tbody>
                  {t.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, c) => (
                        <td key={c} className="border border-border px-3 py-1 font-mono">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {p.images > 0 && (
            <p className="border-t border-border px-4 py-3 text-muted">
              {p.images} image{p.images > 1 ? "s" : ""} on this page. Text extraction cannot read numbers inside an
              image, so a vision model has to describe it in a later stage.
            </p>
          )}
        </section>
      ))}
    </div>
  );
}

export function DocumentDetail({ id }: { id: string }) {
  const [tab, setTab] = useState<"pipeline" | "parsed">("pipeline");
  const v = useQuery({ queryKey: ["version", id], queryFn: () => api.version(id) });
  if (v.isError) return <p className="p-6 text-danger">Document not found.</p>;
  if (!v.data) return null;
  const d = v.data;
  const tabClass = (t: string) =>
    `h-9 whitespace-nowrap px-3 font-medium ${tab === t ? "border-b-2 border-accent text-text" : "text-muted hover:text-text"}`;

  return (
    <div className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-4">
        <a className="text-accent hover:underline" href="#/documents">
          Documents
        </a>
        <h1 className="text-lg font-semibold">{d.title}</h1>
        <span className="font-mono text-muted">
          {d.collection} | v{d.version_label}
          {d.effective_from ? ` | effective ${d.effective_from}` : ""}
          {d.owner_team ? ` | ${d.owner_team}` : ""}
        </span>
        <a className={`${button} ml-auto`} href={`#/compare?a=${d.id}`}>
          Compare with another
        </a>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <iframe
          title={d.title}
          src={api.fileUrl(d.id)}
          className="h-[70vh] md:h-[calc(100vh-6rem)] w-full rounded-ctl border border-border bg-surface"
        />
        <div className="h-[70vh] md:h-[calc(100vh-6rem)] overflow-y-auto">
          <div className="mb-3 flex border-b border-border">
            <button className={tabClass("pipeline")} onClick={() => setTab("pipeline")}>
              Pipeline
            </button>
            <button className={tabClass("parsed")} onClick={() => setTab("parsed")}>
              Parser output
            </button>
          </div>
          {tab === "pipeline" ? <Pipeline id={id} /> : <ParsedView id={id} />}
        </div>
      </div>
    </div>
  );
}
