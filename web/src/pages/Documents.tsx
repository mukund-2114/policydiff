import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type User } from "../api";
import { compareHref, go } from "../router";
import { button, field, panel, primary, td, th } from "../ui";

const ACTIVE = ["queued", "parsing"];

function UploadForm({ collections, onDone }: { collections: string[]; onDone: () => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const upload = useMutation({
    mutationFn: (form: FormData) => api.upload(form),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      if (!res.duplicate) onDone();
    },
  });

  return (
    <form
      className={`${panel} grid gap-3 p-4 sm:grid-cols-2`}
      onSubmit={(e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        if (!form.get("effective_from")) form.delete("effective_from"); // an empty date is not a date
        upload.mutate(form);
      }}
    >
      <label className="space-y-1 sm:col-span-2">
        <span className="text-muted">PDF file</span>
        <input
          className={field}
          type="file"
          name="file"
          accept="application/pdf"
          required
          onChange={(e) => {
            const name = e.target.files?.[0]?.name.replace(/\.pdf$/i, "") ?? "";
            if (!title) setTitle(name);
          }}
        />
      </label>
      <label className="space-y-1">
        <span className="text-muted">Title</span>
        <input className={field} name="title" required value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="space-y-1">
        <span className="text-muted">Collection</span>
        <input className={field} name="collection" defaultValue="General" list="collections" required />
        <datalist id="collections">
          {collections.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </label>
      <label className="space-y-1">
        <span className="text-muted">Version label</span>
        <input className={field} name="version_label" defaultValue="1.0" required />
      </label>
      <label className="space-y-1">
        <span className="text-muted">Effective from</span>
        <input className={field} name="effective_from" type="date" />
      </label>
      <label className="space-y-1">
        <span className="text-muted">Owner team</span>
        <input className={field} name="owner_team" />
      </label>
      <div className="flex items-end gap-3">
        <button className={primary} disabled={upload.isPending}>
          Upload
        </button>
        <button type="button" className={button} onClick={onDone}>
          Cancel
        </button>
      </div>
      {upload.isError && (
        <p role="alert" className="text-danger sm:col-span-2">
          {upload.error instanceof ApiError ? upload.error.message : "Upload failed."}
        </p>
      )}
      {upload.data?.duplicate && (
        <p className="text-muted sm:col-span-2">
          This file is already in the library as {upload.data.version.title} v{upload.data.version.version_label}.
        </p>
      )}
    </form>
  );
}

export function Documents({ user }: { user: User }) {
  const [showUpload, setShowUpload] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const docs = useQuery({
    queryKey: ["documents"],
    queryFn: api.documents,
    // Keep checking while anything is still being processed, so the status updates by itself.
    refetchInterval: (q) => (q.state.data?.some((d) => ACTIVE.includes(d.status)) ? 1500 : false),
  });

  const rows = docs.data ?? [];
  const canUpload = user.role === "admin" || user.role === "reviewer";
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Documents</h1>
        <button
          className={button}
          disabled={selected.length !== 2}
          onClick={() => go(compareHref(selected[0], selected[1]))}
        >
          Compare selected
        </button>
        {canUpload && (
          <button className={primary} onClick={() => setShowUpload(true)}>
            Upload PDF
          </button>
        )}
      </div>

      {showUpload && (
        <UploadForm collections={[...new Set(rows.map((r) => r.collection))]} onDone={() => setShowUpload(false)} />
      )}

      <div className={`${panel} overflow-x-auto`}>
        <table className="w-full border-collapse">
          <thead className="border-b border-border">
            <tr>
              <th className={`${th} w-10`} />
              <th className={th}>Title</th>
              <th className={th}>Collection</th>
              <th className={th}>Version</th>
              <th className={th}>Effective</th>
              <th className={th}>Pages</th>
              <th className={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id} className="border-b border-border last:border-0 hover:bg-bg">
                <td className={td}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${d.title}`}
                    checked={selected.includes(d.id)}
                    onChange={() => toggle(d.id)}
                  />
                </td>
                <td className={td}>
                  <a className="font-medium text-accent hover:underline" href={`#/documents/${d.id}`}>
                    {d.title}
                  </a>
                </td>
                <td className={`${td} text-muted`}>{d.collection}</td>
                <td className={`${td} font-mono`}>{d.version_label}</td>
                <td className={`${td} font-mono`}>{d.effective_from ?? ""}</td>
                <td className={`${td} font-mono`}>{d.pages ?? ""}</td>
                <td className={`${td} font-mono ${d.status === "failed" ? "text-danger" : ""}`}>
                  {d.status}
                  {d.failed_stage ? ` (${d.failed_stage})` : ""}
                </td>
              </tr>
            ))}
            {docs.isSuccess && rows.length === 0 && (
              <tr>
                <td className={`${td} text-muted`} colSpan={7}>
                  No documents yet. Upload a PDF to start.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-muted">Tick two documents to compare them side by side.</p>
    </div>
  );
}
