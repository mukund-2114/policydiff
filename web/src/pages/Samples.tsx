import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { go } from "../router";
import { button, panel, td, th } from "../ui";

export function Samples() {
  const [selected, setSelected] = useState<string[]>([]);
  const policies = useQuery({ queryKey: ["sample-policies"], queryFn: api.samplePolicies });
  const key = useQuery({ queryKey: ["answer-key"], queryFn: api.answerKey });
  if (policies.isError) return <p className="p-6 text-muted">The sample corpus is not installed.</p>;

  const count = (doc: string) =>
    key.data?.conflicts.filter((c) => c.a.doc === doc || c.b.doc === doc).length ?? "";
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Sample policies</h1>
        <button
          className={button}
          disabled={selected.length !== 2}
          onClick={() => go(`#/sample-compare?a=${selected[0]}&b=${selected[1]}`)}
        >
          Compare selected
        </button>
      </div>
      <p className="text-muted">
        Northwind Air is a made-up airline. These 15 policies hold planted conflicts, so you can see what the scanner
        should find. They are read straight from the Markdown files, not uploaded.
      </p>
      <div className={`${panel} overflow-x-auto`}>
        <table className="w-full border-collapse">
          <thead className="border-b border-border">
            <tr>
              <th className={`${th} w-10`} />
              <th className={th}>Policy</th>
              <th className={th}>ID</th>
              <th className={th}>Collection</th>
              <th className={th}>Version</th>
              <th className={th}>Effective</th>
              <th className={th}>Owner</th>
              <th className={th}>Planted conflicts</th>
            </tr>
          </thead>
          <tbody>
            {policies.data?.map((p) => (
              <tr key={p.doc_id} className="border-b border-border last:border-0 hover:bg-bg">
                <td className={td}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${p.title}`}
                    checked={selected.includes(p.doc_id)}
                    onChange={() => toggle(p.doc_id)}
                  />
                </td>
                <td className={td}>
                  <a className="font-medium text-accent hover:underline" href={`#/samples/${p.doc_id}`}>
                    {p.title}
                  </a>
                </td>
                <td className={`${td} font-mono`}>{p.doc_id}</td>
                <td className={`${td} text-muted`}>{p.collection}</td>
                <td className={`${td} font-mono`}>{p.version}</td>
                <td className={`${td} font-mono`}>{p.effective}</td>
                <td className={`${td} text-muted`}>{p.owner}</td>
                <td className={`${td} font-mono`}>{count(p.doc_id)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted">
        Tick two policies to read them side by side, or open the <a className="text-accent hover:underline" href="#/answer-key">answer key</a> to jump to a planted conflict.
      </p>
    </div>
  );
}
