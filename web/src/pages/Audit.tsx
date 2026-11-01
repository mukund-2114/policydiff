import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { button, field, panel, td, th } from "../ui";

// The audit log, newest first. It records who did what: sign in, upload, scan, decisions on
// findings, settings changes and questions asked. Details hold names, ids and counts only, never
// keys or document text. Export CSV downloads the whole log for the chosen action.

const ACTIONS = [
  "login",
  "document_upload",
  "document_delete",
  "login_failed",
  "scan_start",
  "scan_finish",
  "finding_update",
  "settings_change",
  "settings_preview",
  "ask",
];

const PAGE = 100;

export function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const log = useQuery({
    queryKey: ["audit", action, page],
    queryFn: () => api.audit(action, PAGE, page * PAGE),
  });
  const rows = log.data ?? [];
  const csv = `/api/audit.csv${action ? `?action=${encodeURIComponent(action)}` : ""}`;

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">Audit log</h1>
      <div className="flex flex-wrap items-center gap-3">
        <select
          className={`${field} w-56`}
          value={action}
          aria-label="Action"
          onChange={(e) => (setAction(e.target.value), setPage(0))}
        >
          <option value="">All actions</option>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <a className={button} href={csv}>
          Export CSV
        </a>
        <p className="text-muted">Page {page + 1}, newest first.</p>
      </div>
      {log.isError && <p className="text-danger">Only an admin can open the audit log.</p>}
      {log.isSuccess && rows.length === 0 && <p className="text-muted">No events match this filter.</p>}
      {rows.length > 0 && (
        <div className={`${panel} overflow-x-auto`}>
          <table className="w-full">
            <thead className="border-b border-border">
              <tr>
                <th className={th}>Time</th>
                <th className={th}>User</th>
                <th className={th}>Action</th>
                <th className={th}>Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className={`${td} whitespace-nowrap font-mono`}>{e.at.replace("T", " ").slice(0, 19)}</td>
                  <td className={td}>{e.user ?? "system"}</td>
                  <td className={`${td} font-mono`}>{e.action}</td>
                  <td className={`${td} break-all font-mono text-muted`}>
                    {[e.target, e.detail ? JSON.stringify(e.detail) : null].filter(Boolean).join(" ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex gap-2">
        <button className={button} disabled={page === 0} onClick={() => setPage(page - 1)}>
          Newer
        </button>
        <button className={button} disabled={rows.length < PAGE} onClick={() => setPage(page + 1)}>
          Older
        </button>
      </div>
    </div>
  );
}
