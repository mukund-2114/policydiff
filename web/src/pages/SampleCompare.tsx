import { useQuery } from "@tanstack/react-query";
import { api, type AnswerSide } from "../api";
import { PolicyView } from "../components/PolicyView";
import { go, useRoute } from "../router";
import { button, field, panel } from "../ui";

const href = (a?: string | null, b?: string | null) => {
  const q = new URLSearchParams();
  if (a) q.set("a", a);
  if (b) q.set("b", b);
  return `#/sample-compare?${q.toString()}`;
};

function Pane({ id, mark }: { id: string | null; mark?: AnswerSide }) {
  const policy = useQuery({ queryKey: ["sample-policy", id], queryFn: () => api.samplePolicy(id!), enabled: !!id });
  if (!id) {
    return (
      <div className="flex h-full items-center justify-center rounded-ctl border border-dashed border-border text-muted">
        Choose a policy above.
      </div>
    );
  }
  if (!policy.data) return <div className={`${panel} h-full`} />;
  const p = policy.data;
  return (
    <article className={`${panel} flex h-full min-h-0 flex-col`}>
      <header className="border-b border-border px-4 py-2">
        <p className="font-medium">{p.title}</p>
        <p className="font-mono text-muted">
          {p.doc_id} | v{p.version} | effective {p.effective} | {p.owner}
        </p>
        {mark && (
          <p className="mt-1">
            <span className="text-muted">
              {mark.kind === "figure" ? `Value in ${mark.ref} (image only):` : `${mark.ref}:`}
            </span>{" "}
            <span className="font-mono">{mark.text}</span>
          </p>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <PolicyView markdown={p.markdown} marks={mark ? [mark] : []} />
      </div>
    </article>
  );
}

export function SampleCompare() {
  const { query } = useRoute();
  const key = useQuery({ queryKey: ["answer-key"], queryFn: api.answerKey });
  const policies = useQuery({ queryKey: ["sample-policies"], queryFn: api.samplePolicies });

  // ?item=C01 opens both policies of that answer-key entry with the planted sentences marked.
  const item = [...(key.data?.conflicts ?? []), ...(key.data?.near_misses ?? [])].find((i) => i.id === query.get("item"));
  const a = item?.a.doc ?? query.get("a");
  const b = item?.b.doc ?? query.get("b");

  const picker = (label: string, value: string | null, set: (v: string) => void) => (
    <label className="flex min-w-0 flex-1 items-center gap-2">
      <span className="text-muted">{label}</span>
      <select className={field} value={value ?? ""} onChange={(e) => set(e.target.value)}>
        <option value="">Choose a policy</option>
        {policies.data?.map((p) => (
          <option key={p.doc_id} value={p.doc_id}>
            {p.title} ({p.doc_id})
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex min-h-[32rem] md:h-screen flex-col gap-3 px-4 py-4">
      {item && (
        <div className={`${panel} flex flex-wrap items-baseline gap-x-4 px-4 py-2`}>
          <span className="font-mono font-medium">{item.id}</span>
          <span className="font-mono text-muted">{item.type ?? "near miss, consistent"}</span>
          <span>{item.note}</span>
          <a className="ml-auto text-accent hover:underline" href="#/answer-key">
            Back to answer key
          </a>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {picker("Left", a, (v) => go(href(v, b)))}
        <button className={button} onClick={() => go(href(b, a))}>
          Swap
        </button>
        {picker("Right", b, (v) => go(href(a, v)))}
      </div>
      <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-2">
        <Pane id={a} mark={item?.a} />
        <Pane id={b} mark={item?.b} />
      </div>
    </div>
  );
}
