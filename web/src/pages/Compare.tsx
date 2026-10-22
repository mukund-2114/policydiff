import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { compareHref, go, useRoute } from "../router";
import { button, field, versionName } from "../ui";

export function Compare() {
  const { query } = useRoute();
  const a = query.get("a");
  const b = query.get("b");
  const docs = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  const options = docs.data ?? [];

  const picker = (label: string, value: string | null, set: (v: string) => void) => (
    <label className="flex min-w-0 flex-1 items-center gap-2">
      <span className="text-muted">{label}</span>
      <select className={field} value={value ?? ""} onChange={(e) => set(e.target.value)}>
        <option value="">Choose a document</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {versionName(o)}
          </option>
        ))}
      </select>
    </label>
  );

  const pane = (id: string | null) =>
    id ? (
      <iframe title={id} src={api.fileUrl(id)} className="h-full w-full rounded-ctl border border-border bg-surface" />
    ) : (
      <div className="flex h-full items-center justify-center rounded-ctl border border-dashed border-border text-muted">
        Choose a document above.
      </div>
    );

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-3 px-4 py-4">
      <div className="flex flex-wrap items-center gap-3">
        {picker("Left", a, (v) => go(compareHref(v, b)))}
        <button className={button} onClick={() => go(compareHref(b, a))}>
          Swap
        </button>
        {picker("Right", b, (v) => go(compareHref(a, v)))}
      </div>
      <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-2">
        {pane(a)}
        {pane(b)}
      </div>
    </div>
  );
}
