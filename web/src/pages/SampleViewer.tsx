import { useQuery } from "@tanstack/react-query";
import { api, type AnswerItem } from "../api";
import { PolicyView } from "../components/PolicyView";
import { panel } from "../ui";

function Related({ title, items, doc }: { title: string; items: AnswerItem[]; doc: string }) {
  if (items.length === 0) return null;
  return (
    <section className={panel}>
      <h2 className="border-b border-border px-4 py-2 font-medium">{title}</h2>
      <ul>
        {items.map((i) => {
          const here = i.a.doc === doc ? i.a : i.b;
          const other = i.a.doc === doc ? i.b : i.a;
          return (
            <li key={i.id} className="space-y-1 border-b border-border px-4 py-3 last:border-0">
              <p>
                <span className="font-mono">{i.id}</span> <span className="font-mono text-muted">{i.type ?? "consistent"}</span>
              </p>
              <p className="text-muted">
                Clause {here.ref} and {other.title} {other.ref}. {i.note}
              </p>
              <a className="text-accent hover:underline" href={`#/sample-compare?item=${i.id}`}>
                Compare
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function SampleViewer({ id }: { id: string }) {
  const policy = useQuery({ queryKey: ["sample-policy", id], queryFn: () => api.samplePolicy(id) });
  const key = useQuery({ queryKey: ["answer-key"], queryFn: api.answerKey });
  if (policy.isError) return <p className="p-6 text-danger">Policy not found.</p>;
  if (!policy.data) return null;
  const p = policy.data;
  const involves = (i: AnswerItem) => i.a.doc === id || i.b.doc === id;

  return (
    <div className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-4">
        <a className="text-accent hover:underline" href="#/samples">
          Sample policies
        </a>
        <h1 className="text-lg font-semibold">{p.title}</h1>
        <span className="font-mono text-muted">
          {p.doc_id} | {p.collection} | v{p.version} | effective {p.effective} | {p.owner}
        </span>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <article className={`${panel} h-[70vh] md:h-[calc(100vh-5rem)] overflow-y-auto p-6`}>
          <PolicyView markdown={p.markdown} marks={[]} />
        </article>
        <aside className="h-[70vh] md:h-[calc(100vh-5rem)] space-y-4 overflow-y-auto">
          <Related title="Planted conflicts" items={key.data?.conflicts.filter(involves) ?? []} doc={id} />
          <Related title="Near misses" items={key.data?.near_misses.filter(involves) ?? []} doc={id} />
        </aside>
      </div>
    </div>
  );
}
