import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type SearchHit } from "../api";
import { button, field, panel, primary } from "../ui";

// A page for trying the hybrid search by hand. Two ways in:
//   - type any text (the api embeds it), or
//   - press "Find related" on a result, which does what the scan will do for each clause:
//     use that clause as the query and leave out its own document version.
// "Meaning" and "Words" are the place each hit held in the two searches, before they were merged.

type Mode = { kind: "text"; query: string } | { kind: "related"; hit: SearchHit };

function Rank({ label, rank }: { label: string; rank: number | null }) {
  return (
    <span className={rank ? "text-text" : "text-muted"}>
      {label} {rank ?? "none"}
    </span>
  );
}

export function Search() {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode | null>(null);

  const results = useQuery({
    queryKey: ["search", mode?.kind, mode?.kind === "text" ? mode.query : mode?.hit.chunk_id],
    queryFn: () => (mode!.kind === "text" ? api.search(mode!.query) : api.related(mode!.hit.chunk_id)),
    enabled: mode !== null,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-6">
      <h1 className="text-lg font-semibold">Search</h1>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) setMode({ kind: "text", query: input.trim() });
        }}
      >
        <input
          className={field}
          placeholder="For example: deadline to submit expense claims"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className={primary} disabled={!input.trim()}>
          Search
        </button>
      </form>

      {mode?.kind === "related" && (
        <div className={`${panel} space-y-1 p-3`}>
          <p className="text-muted">
            Clauses related to {mode.hit.title} v{mode.hit.version_label}, {mode.hit.heading_path}. Its own version is left out.
          </p>
          <p className="whitespace-pre-wrap">{mode.hit.text}</p>
        </div>
      )}

      {results.isFetching && <p className="text-muted">Searching</p>}
      {results.isError && (
        <p role="alert" className="text-danger">
          {(results.error as Error).message}
        </p>
      )}
      {results.isSuccess && results.data.length === 0 && <p className="text-muted">No results.</p>}

      <ol className="space-y-3">
        {results.data?.map((h, i) => (
          <li key={h.chunk_id} className={`${panel} space-y-2 p-3`}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-muted">{i + 1}</span>
              <span className="font-medium">
                {h.title} v{h.version_label}
              </span>
              <span className="text-muted">
                {h.heading_path}
                {h.page ? `, page ${h.page}` : ""}
              </span>
              <span className="ml-auto flex gap-3 text-xs">
                <Rank label="Meaning" rank={h.vector_rank} />
                <Rank label="Words" rank={h.keyword_rank} />
                <span className="text-muted">score {h.score.toFixed(4)}</span>
              </span>
            </div>
            <p className="line-clamp-4 whitespace-pre-wrap">{h.text}</p>
            <button className={button} onClick={() => setMode({ kind: "related", hit: h })}>
              Find related
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
