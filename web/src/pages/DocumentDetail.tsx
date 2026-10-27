import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Chunk, type ParsedPage, type Scan, type Stage, type User } from "../api";
import { go } from "../router";
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

const SCAN_ACTIVE = ["queued", "running"];

// A spinner, a bar and a line of numbers, so a running scan is visibly doing something.
// The scan does not know how many pairs it will judge, so the bar counts clauses instead.
function ScanProgress({ scan }: { scan?: Scan }) {
  const p = scan?.progress;
  const pct = p ? Math.round(((p.clause - 1) / p.of) * 100) : 0;
  return (
    <div className="flex min-w-64 flex-1 items-center gap-3" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent" />
      <div className="flex-1">
        <div className="h-2 overflow-hidden rounded bg-border">
          <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1 text-muted">
          {p
            ? `Checking clause ${p.clause} of ${p.of}. ${scan?.judge_calls ?? 0} pairs judged so far.`
            : "Starting the scan..."}
        </p>
      </div>
    </div>
  );
}

// Starts a conflict scan of this version and shows how the latest one is going.
function ScanBar({ id, ready, canScan }: { id: string; ready: boolean; canScan: boolean }) {
  const qc = useQueryClient();
  const scans = useQuery({
    queryKey: ["scans", id],
    queryFn: () => api.scans(id),
    refetchInterval: (q) => (q.state.data?.some((s: Scan) => SCAN_ACTIVE.includes(s.status)) ? 3000 : false),
  });
  const start = useMutation({
    mutationFn: () => api.startScan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scans", id] }),
  });
  const latest = scans.data?.[0];
  const running = latest ? SCAN_ACTIVE.includes(latest.status) : false;
  const s = latest?.stats;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      {canScan && (
        <button className={button} disabled={!ready || running || start.isPending} onClick={() => start.mutate()}>
          {running || start.isPending ? "Scanning..." : "Scan for conflicts"}
        </button>
      )}
      {(running || start.isPending) && <ScanProgress scan={running ? latest : undefined} />}
      {latest && !running && (
        <p className="text-muted">
          Last scan: {latest.status}
          {s && `. ${s.clauses} clauses, ${s.judged} pairs judged, ${s.cached} already judged, ${s.findings} findings`}
          {s && s.unverified > 0 && `, ${s.unverified} dropped (quote not in the text)`}
          {s && s.failed > 0 && `, ${s.failed} pairs failed`}
          {latest.error && `. ${latest.error}`}
        </p>
      )}
      {latest?.status === "done" && (
        <a className="text-accent hover:underline" href="#/findings">
          See findings
        </a>
      )}
      {start.isError && <p className="text-danger">{(start.error as Error).message}</p>}
    </div>
  );
}

export function DocumentDetail({ id, user }: { id: string; user: User }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      go("#/documents");
    },
  });
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
        {user.role === "admin" && (
          <button
            className={`${button} text-danger`}
            disabled={remove.isPending}
            onClick={() => window.confirm(`Delete ${d.title} v${d.version_label}? This removes its file, chunks and findings.`) && remove.mutate()}
          >
            Delete
          </button>
        )}
      </div>
      {remove.isError && <p className="mb-2 text-danger">{(remove.error as Error).message}</p>}
      <div className="mb-4">
        <PipelineStepper v={d} onOpenTab={setTab} />
      </div>
      <ScanBar id={id} ready={d.status === "ready"} canScan={user.role === "admin" || user.role === "reviewer"} />
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
