import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type AnswerItem, type AnswerSide } from "../api";
import { field, panel, td, th } from "../ui";

const KIND_LABEL = { clause: "Text", table: "Table", figure: "Figure" } as const;

function Side({ s }: { s: AnswerSide }) {
  return (
    <div className="space-y-1">
      <p className="font-medium">
        {s.title} <span className="font-mono font-normal text-muted">{s.doc} {s.ref}</span>
      </p>
      <p className="font-mono text-muted">{s.text}</p>
    </div>
  );
}

function Row({ item }: { item: AnswerItem }) {
  return (
    <tr className="border-t border-border">
      <td className={`${td} font-mono`}>{item.id}</td>
      <td className={td}>
        {item.type ? <span className="font-mono">{item.type}</span> : <span className="text-muted">consistent</span>}
        <p className="text-muted">{KIND_LABEL[item.a.kind]} and {KIND_LABEL[item.b.kind].toLowerCase()}</p>
      </td>
      <td className={td}>
        <Side s={item.a} />
      </td>
      <td className={td}>
        <Side s={item.b} />
      </td>
      <td className={td}>
        <p>{item.note}</p>
        <a className="text-accent hover:underline" href={`#/sample-compare?item=${item.id}`}>
          Compare
        </a>
      </td>
    </tr>
  );
}

export function AnswerKey() {
  const [tab, setTab] = useState<"conflicts" | "near_misses">("conflicts");
  const [type, setType] = useState("");
  const key = useQuery({ queryKey: ["answer-key"], queryFn: api.answerKey });
  if (key.isError) return <p className="p-6 text-muted">The sample corpus is not installed.</p>;
  if (!key.data) return null;

  const items = key.data[tab].filter((i) => !type || i.type === type || i.modality === type);
  const types = [...new Set(key.data.conflicts.flatMap((c) => [c.type!, c.modality!]))];
  const tabClass = (t: string) =>
    `h-9 whitespace-nowrap px-3 font-medium ${tab === t ? "border-b-2 border-accent text-text" : "text-muted hover:text-text"}`;

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <div>
        <h1 className="text-lg font-semibold">Sample answer key</h1>
        <p className="text-muted">
          The Northwind Air policies hold 25 planted conflicts and 25 near misses that look alike but agree. Use this
          list to check what the scanner should find. Compare opens both policies with the planted sentences marked.
        </p>
      </div>
      <div className="flex items-center gap-3 border-b border-border">
        <button className={tabClass("conflicts")} onClick={() => setTab("conflicts")}>
          Conflicts ({key.data.conflicts.length})
        </button>
        <button className={tabClass("near_misses")} onClick={() => setTab("near_misses")}>
          Near misses ({key.data.near_misses.length})
        </button>
        {tab === "conflicts" && (
          <select className={`${field} mb-1 ml-auto w-56`} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className={`${panel} overflow-x-auto`}>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={`${th} w-14`}>ID</th>
              <th className={`${th} w-40`}>Type</th>
              <th className={th}>Side A</th>
              <th className={th}>Side B</th>
              <th className={`${th} w-56`}>Why</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <Row key={i.id} item={i} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
