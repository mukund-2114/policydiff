import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Chunk, type ParsedPage, type Stage } from "../api";
import { PipelineStepper } from "../components/PipelineStepper";
import { button, formatDuration, panel, td, th } from "../ui";

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
  const qc = useQueryClient();
  const reembed = useMutation({
    mutationFn: () => api.reembed(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["version", id] }),
  });
  const reparse = useMutation({
    mutationFn: () => api.reparse(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["version", id] });
      qc.invalidateQueries({ queryKey: ["chunks", id] });
    },
  });
  const v = useQuery({
    queryKey: ["version", id],
    queryFn: () => api.version(id),
    refetchInterval: (q) => (q.state.data && ["queued", "parsing", "parsed", "chunking", "chunked", "embedding"].includes(q.state.data.status) ? 1000 : false),
  });
  if (!v.data) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <p className="text-muted">
          Status: <span className="font-mono text-text">{v.data.status}</span>
        </p>
        <div className="ml-auto flex gap-2">
          <button className={button} disabled={reembed.isPending} onClick={() => reembed.mutate()}>
            Embed again
          </button>
          <button className={button} disabled={reparse.isPending} onClick={() => reparse.mutate()}>
            Parse again
          </button>
        </div>
      </div>
      {reembed.isError && <p className="text-danger">{(reembed.error as Error).message}</p>}
      {reparse.isError && <p className="text-danger">{(reparse.error as Error).message}</p>}
      <ol className={panel}>
        <li className="flex items-baseline gap-3 border-b border-border px-4 py-3">
          <span className="font-medium">Upload</span>
          <span className="font-mono text-muted">done</span>
          <span className="ml-auto text-muted">File stored, duplicate check passed</span>
        </li>
        {v.data.stages.map((s) => (
          <StageRow key={s.started_at} s={s} />
        ))}
      </ol>
    </div>
  );
}

function ChunksView({ id }: { id: string }) {
  const qc = useQueryClient();
  const chunks = useQuery({ queryKey: ["chunks", id], queryFn: () => api.chunks(id) });
  const rechunk = useMutation({
    mutationFn: () => api.rechunk(id),
    onSuccess: () => {
      // The job runs in the worker, so check again shortly instead of waiting for a page reload.
      for (const ms of [1500, 4000]) {
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["chunks", id] });
          qc.invalidateQueries({ queryKey: ["version", id] });
        }, ms);
      }
    },
  });
  if (!chunks.data) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <p className="text-muted">
          {chunks.data.length} chunks. The line above each one is added in front of the text before it is embedded.
        </p>
        <button className={`${button} ml-auto`} disabled={rechunk.isPending} onClick={() => rechunk.mutate()}>
          Cut again
        </button>
      </div>
      {rechunk.isError && <p className="text-danger">{(rechunk.error as Error).message}</p>}
      {chunks.data.length === 0 && <p className="text-muted">No chunks yet. They appear after the document is parsed.</p>}
      <ol className="space-y-3">
        {chunks.data.map((c: Chunk) => (
          <li key={c.position} className={`${panel} px-4 py-3`}>
            <p className="font-mono text-muted">
              {c.position + 1} | page {c.page} | {c.kind} | {c.embedding_model ? "embedded" : "not embedded"}
            </p>
            {c.context_header && <p className="mt-1 text-muted">{c.context_header}</p>}
            <p className="mt-1 whitespace-pre-wrap">{c.text}</p>
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
  const [tab, setTab] = useState<"pipeline" | "chunks" | "parsed">("pipeline");
  // Hiding the PDF gives the tabs the full width. The choice is remembered between visits.
  const [showPdf, setShowPdf] = useState(() => {
    try {
      return localStorage.getItem("showPdf") !== "no";
    } catch {
      return true;
    }
  });
  const togglePdf = () => {
    setShowPdf(!showPdf);
    try {
      localStorage.setItem("showPdf", showPdf ? "no" : "yes");
    } catch {
      /* the page still works when storage is blocked */
    }
  };
  // Polled while work is going on, so the steps move by themselves. The Pipeline tab shares this query.
  const v = useQuery({
    queryKey: ["version", id],
    queryFn: () => api.version(id),
    refetchInterval: (q) =>
      q.state.data && ["queued", "parsing", "parsed", "chunking", "chunked", "embedding"].includes(q.state.data.status) ? 1000 : false,
  });
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
          {d.status === "superseded" ? ` | superseded${d.effective_to ? ` on ${d.effective_to}` : ""}` : ""}
          {d.owner_team ? ` | ${d.owner_team}` : ""}
        </span>
        <button className={`${button} ml-auto`} onClick={togglePdf} aria-pressed={!showPdf}>
          {showPdf ? "Hide PDF" : "Show PDF"}
        </button>
        <a className={button} href={`#/compare?a=${d.id}`}>
          Compare with another
        </a>
      </div>
      <div className="mb-4">
        <PipelineStepper v={d} onOpenTab={setTab} />
      </div>
      <div className={`grid gap-4 ${showPdf ? "lg:grid-cols-2" : ""}`}>
        {showPdf && (
          <iframe
            title={d.title}
            src={api.fileUrl(d.id)}
            className="h-[70vh] md:h-[calc(100vh-6rem)] w-full rounded-ctl border border-border bg-surface"
          />
        )}
        <div className="h-[70vh] md:h-[calc(100vh-6rem)] overflow-y-auto">
          <div className="mb-3 flex border-b border-border">
            <button className={tabClass("pipeline")} onClick={() => setTab("pipeline")}>
              Pipeline
            </button>
            <button className={tabClass("chunks")} onClick={() => setTab("chunks")}>
              Chunks
            </button>
            <button className={tabClass("parsed")} onClick={() => setTab("parsed")}>
              Parser output
            </button>
          </div>
          {tab === "pipeline" && <Pipeline id={id} />}
          {tab === "chunks" && <ChunksView id={id} />}
          {tab === "parsed" && <ParsedView id={id} />}
        </div>
      </div>
    </div>
  );
}
