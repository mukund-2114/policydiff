import { useEffect, useRef, useState } from "react";
import { askStream, type AskEvent, type AskFinding, type AskPassage } from "../api";
import { button, field, panel } from "../ui";

// A chat over the policy library. Each message is answered from the passages the search finds, and
// the answer appears as it is written. Citations like [1] point at the passages listed under the
// answer. Findings that involve a cited passage are listed too. The whole conversation is sent with
// each message, so a follow-up such as "and for contractors?" works. An "as of" date searches the
// versions that were in effect on that day.

type Message = {
  role: "user" | "assistant";
  text: string;
  passages?: AskPassage[];
  rewrites?: string[]; // other wordings searched with the question (multi-query)
  cited?: number[];
  findings?: AskFinding[];
  seconds?: number;
  error?: string;
  streaming?: boolean;
};

const TYPE = {
  numeric_mismatch: "Numbers differ",
  obligation_conflict: "Obligations conflict",
  scope_overlap: "Scope overlap",
  definition_mismatch: "Definitions differ",
  outdated_reference: "Outdated reference",
} as Record<string, string>;

const EXAMPLES = [
  "How long do I have to submit an expense claim?",
  "What is the minimum password length?",
  "How many bags can an economy passenger check?",
];

// The sources sit in a closed list under the answer. A click on a marker opens it and scrolls there.
function openSource(p: AskPassage) {
  const item = document.getElementById(`source-${p.n}-${p.chunk_id}`);
  const list = item?.closest("details");
  if (list) list.open = true;
  item?.scrollIntoView({ block: "center" });
}

// Turns "[1]" in the text into a small marker that names the document when you hover it.
function WithCitations({ text, passages }: { text: string; passages: AskPassage[] }) {
  return (
    <>
      {text.split(/(\[\d+\])/).map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        const p = m && passages.find((x) => x.n === Number(m[1]));
        if (!p) return <span key={i}>{part}</span>;
        return (
          <button
            key={i}
            type="button"
            title={`${p.title} v${p.version_label}, ${p.heading_path ?? ""}`}
            className="mx-0.5 rounded-ctl border border-border bg-bg px-1 font-mono text-xs text-accent hover:bg-accent-soft"
            onClick={() => openSource(p)}
          >
            {p.n}
          </button>
        );
      })}
    </>
  );
}

function Sources({ m }: { m: Message }) {
  const shown = (m.passages ?? []).filter((p) => m.cited?.includes(p.n));
  if (shown.length === 0) return null;
  return (
    <details className="text-muted">
      <summary className="cursor-pointer">
        {shown.length} source{shown.length === 1 ? "" : "s"}
      </summary>
      <ol className="mt-2 space-y-2">
        {shown.map((p) => (
          <li key={p.chunk_id} id={`source-${p.n}-${p.chunk_id}`} className={`${panel} px-3 py-2 text-text`}>
            <p className="text-muted">
              <span className="font-mono">[{p.n}]</span>{" "}
              <a className="text-accent hover:underline" href={`#/documents/${p.version_id}`}>
                {p.title} v{p.version_label}
              </a>
              , {p.heading_path}
              {p.page ? `, page ${p.page}` : ""}
            </p>
            <p className="mt-1 whitespace-pre-wrap">{p.text}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Findings({ items }: { items: AskFinding[] }) {
  if (items.length === 0) return null;
  return (
    <div className={`${panel} space-y-1 border-warn px-3 py-2`}>
      <p className="font-medium">
        {items.length} finding{items.length === 1 ? "" : "s"} on these passages
      </p>
      <ul className="divide-y divide-border">
        {items.map((f) => (
          <li key={f.id} className="py-1.5">
            <span className="font-medium">{TYPE[f.type] ?? f.type}</span>
            <span className="ml-2 text-muted">
              {f.between}, {f.status}, {(f.confidence * 100).toFixed(0)}%
            </span>
            <p>{f.explanation}</p>
          </li>
        ))}
      </ul>
      <a className="text-accent hover:underline" href="#/findings">
        Open the review queue
      </a>
    </div>
  );
}

function Turn({ m }: { m: Message }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-ctl bg-accent-soft px-3 py-2">{m.text}</p>
      </div>
    );
  }
  return (
    <div className="max-w-[92%] space-y-2">
      <p className="whitespace-pre-wrap">
        {m.text ? <WithCitations text={m.text} passages={m.passages ?? []} /> : m.streaming ? "Searching the policies" : ""}
        {m.streaming && <span className="ml-0.5 animate-pulse text-muted">|</span>}
      </p>
      {m.error && <p className="text-danger">{m.error}</p>}
      {!m.streaming && <Sources m={m} />}
      {!m.streaming && (m.rewrites?.length ?? 0) > 0 && (
        <p className="text-muted">Also searched as: {m.rewrites!.join("; ")}</p>
      )}
      {!m.streaming && <Findings items={m.findings ?? []} />}
      {!m.streaming && m.seconds !== undefined && <p className="text-xs text-muted">{m.seconds} s</p>}
    </div>
  );
}

export function Ask() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [asOf, setAsOf] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // Braces matter: an effect must return nothing or a cleanup function, never a value.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  useEffect(() => {
    if (!busy) box.current?.focus();
  }, [busy]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    const history = messages.filter((m) => m.text && !m.error).map((m) => ({ role: m.role, content: m.text }));
    setInput("");
    setBusy(true);
    setMessages((all) => [...all, { role: "user", text: question }, { role: "assistant", text: "", streaming: true }]);
    const patch = (change: (m: Message) => Message) =>
      setMessages((all) => all.map((m, i) => (i === all.length - 1 ? change(m) : m)));
    try {
      for await (const event of askStream({ question, history, as_of: asOf || null })) {
        const e: AskEvent = event;
        if (e.type === "passages") patch((m) => ({ ...m, passages: e.passages, rewrites: e.rewrites }));
        else if (e.type === "token") patch((m) => ({ ...m, text: m.text + e.text }));
        else if (e.type === "done")
          patch((m) => ({ ...m, streaming: false, cited: e.cited, findings: e.findings, seconds: e.seconds }));
        else if (e.type === "error") patch((m) => ({ ...m, streaming: false, error: e.message }));
      }
    } catch (err) {
      patch((m) => ({ ...m, streaming: false, error: (err as Error).message }));
    } finally {
      patch((m) => ({ ...m, streaming: false }));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col px-4">
      <div className="flex flex-wrap items-center gap-3 py-4">
        <h1 className="mr-auto text-lg font-semibold">Ask</h1>
        <label className="flex items-center gap-2 whitespace-nowrap text-muted">
          As of
          <input
            className={`${field} w-40`}
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            aria-label="As of date"
          />
        </label>
        <button className={button} disabled={busy || messages.length === 0} onClick={() => setMessages([])}>
          New chat
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-3 pt-8">
            <p className="text-muted">
              Ask about your policies. Answers come from the documents in the library and cite where they found
              each statement. Follow-up questions work. With a date, the search covers the versions in effect that day;
              a version with no effective date counts as always in effect.
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((q) => (
                <button key={q} className={button} onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <Turn key={i} m={m} />
        ))}
        <div ref={end} />
      </div>

      <form
        className="flex items-end gap-2 border-t border-border bg-bg py-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          ref={box}
          className={`${field} h-auto min-h-9 resize-none py-1.5`}
          rows={1}
          placeholder="Ask a question. Enter sends, Shift+Enter adds a line."
          value={input}
          disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          aria-label="Message"
        />
        <button className={`${button} bg-accent text-accent-text hover:opacity-90`} disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
