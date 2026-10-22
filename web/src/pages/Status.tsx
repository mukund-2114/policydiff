import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { panel } from "../ui";

export function Status() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const h = health.data;
  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">System status</h1>
      <dl className={`${panel} grid grid-cols-[8rem_1fr] gap-y-1 p-4`}>
        <dt className="text-muted">Overall</dt>
        <dd className="font-mono">{h?.status ?? "checking"}</dd>
        <dt className="text-muted">Database</dt>
        <dd className="font-mono">{h?.db ?? "checking"}</dd>
        <dt className="text-muted">Chat model</dt>
        <dd className="font-mono">{h?.models.chat ?? "not configured"}</dd>
        <dt className="text-muted">Embeddings</dt>
        <dd className="font-mono">{h?.models.embed ?? "not configured"}</dd>
        {h?.models.error && (
          <>
            <dt className="text-muted">Model issue</dt>
            <dd className="text-warn">{h.models.error}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
