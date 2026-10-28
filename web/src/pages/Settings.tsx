import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type ModelPick, type RerankPick, type SettingsData } from "../api";
import { button, field, panel, primary } from "../ui";

// The Settings page, for admins. Three blocks: provider keys, which model each job uses, and a
// Preview that tries the choices on 20 random chunks before you rely on them. A key is tested
// before it is saved, is stored encrypted, and is never shown again, so the page only says whether
// one is set and where it comes from.

const PROVIDERS = [
  { id: "openai", label: "OpenAI", note: "Embeddings, the judge and Q&A use this by default." },
  { id: "anthropic", label: "Anthropic", note: "Only needed if you pick a Claude model below." },
  { id: "cohere", label: "Cohere", note: "Only needed for the Cohere reranker. Chunk text is sent to Cohere." },
] as const;

const SOURCE = { settings: "Saved here", env: "Set in .env" } as const;

function KeyRow({ id, label, note, state }: { id: string; label: string; note: string; state: SettingsData["keys"][string] }) {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const test = useMutation({
    mutationFn: () => api.testKey(id, value.trim() || undefined),
    onSuccess: (r) => setMessage({ ok: r.ok, text: r.message }),
    onError: (e: Error) => setMessage({ ok: false, text: e.message }),
  });
  const save = useMutation({
    mutationFn: (key: string | null) => api.saveSettings({ keys: { [id]: key } }),
    onSuccess: (_, key) => {
      setValue("");
      setMessage({ ok: true, text: key ? "Key tested and saved." : "Key removed." });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => setMessage({ ok: false, text: e.message }),
  });
  return (
    <div className="space-y-2 border-t border-border py-3 first:border-t-0">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="font-medium">{label}</span>
        <span className={`font-mono ${state.set ? "text-ok" : "text-muted"}`}>
          {state.source ? SOURCE[state.source] : "Not set"}
        </span>
        <span className="text-muted">{note}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          className={`${field} max-w-md`}
          type="password"
          autoComplete="off"
          placeholder={state.set ? "Enter a new key to replace it" : "Paste a key"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label={`${label} key`}
        />
        <button className={button} disabled={test.isPending || (!value.trim() && !state.set)} onClick={() => test.mutate()}>
          Test key
        </button>
        <button className={primary} disabled={save.isPending || !value.trim()} onClick={() => save.mutate(value.trim())}>
          Save key
        </button>
        {state.source === "settings" && (
          <button className={button} disabled={save.isPending} onClick={() => save.mutate(null)}>
            Remove key
          </button>
        )}
      </div>
      {message && <p className={message.ok ? "text-ok" : "text-danger"}>{message.text}</p>}
    </div>
  );
}

function ModelRow({ label, note, value, onChange }: { label: string; note: string; value: ModelPick; onChange: (v: ModelPick) => void }) {
  return (
    <div className="grid items-center gap-2 border-t border-border py-3 first:border-t-0 md:grid-cols-[12rem_10rem_1fr]">
      <div>
        <p className="font-medium">{label}</p>
        <p className="text-muted">{note}</p>
      </div>
      <select
        className={field}
        value={value.provider}
        aria-label={`${label} provider`}
        onChange={(e) => onChange({ ...value, provider: e.target.value as ModelPick["provider"] })}
      >
        <option value="openai">OpenAI</option>
        <option value="anthropic">Anthropic</option>
        <option value="ollama">Ollama (local)</option>
      </select>
      <input
        className={field}
        value={value.model}
        aria-label={`${label} model`}
        onChange={(e) => onChange({ ...value, model: e.target.value })}
      />
    </div>
  );
}

export function Settings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [chat, setChat] = useState<ModelPick | null>(null);
  const [vision, setVision] = useState<ModelPick | null>(null);
  const [rerank, setRerank] = useState<RerankPick | null>(null);

  useEffect(() => {
    if (settings.data) {
      setChat(settings.data.chat);
      setVision(settings.data.vision);
      setRerank(settings.data.rerank);
    }
  }, [settings.data]);

  const choices = chat && vision && rerank ? { chat, vision, rerank } : null;
  const save = useMutation({
    mutationFn: () => api.saveSettings(choices!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const preview = useMutation({ mutationFn: () => api.previewSettings(choices!) });

  if (settings.isError) return <p className="p-6 text-danger">Only an admin can open Settings.</p>;
  if (!settings.data || !choices) return null;
  const s = settings.data;
  const dirty = JSON.stringify(choices) !== JSON.stringify({ chat: s.chat, vision: s.vision, rerank: s.rerank });
  const p = preview.data;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6">
      <h1 className="text-lg font-semibold">Settings</h1>

      <section className={`${panel} px-4 py-2`}>
        <h2 className="pt-2 font-medium">Provider keys</h2>
        <p className="text-muted">
          A key is tested before it is saved and stored encrypted. It is not shown again. A key saved here is used
          instead of the one in .env.
        </p>
        {PROVIDERS.map((x) => (
          <KeyRow key={x.id} {...x} state={s.keys[x.id]} />
        ))}
      </section>

      <section className={`${panel} px-4 py-2`}>
        <h2 className="pt-2 font-medium">Models</h2>
        <p className="text-muted">Changes apply to the next scan, question or upload. Nothing restarts.</p>
        <ModelRow label="Judge and Q&A" note="Reads pairs and answers questions." value={chat!} onChange={setChat} />
        <ModelRow label="Figures" note="Reads charts and drawings." value={vision!} onChange={setVision} />
        <div className="grid items-center gap-2 border-t border-border py-3 md:grid-cols-[12rem_10rem_1fr]">
          <div>
            <p className="font-medium">Reranker</p>
            <p className="text-muted">Orders candidate pairs.</p>
          </div>
          <select
            className={field}
            value={rerank!.provider}
            aria-label="Reranker"
            onChange={(e) => setRerank({ provider: e.target.value as RerankPick["provider"], model: null })}
          >
            <option value="local">Local, runs here</option>
            <option value="llm">Chat model</option>
            <option value="cohere">Cohere</option>
          </select>
          <p className="text-muted">
            {rerank!.provider === "cohere"
              ? "Cohere receives the text of each chunk it ranks."
              : rerank!.provider === "llm"
                ? "Uses the judge model, so it adds one model call per chunk."
                : "Nothing leaves this machine."}
          </p>
        </div>
        <div className="grid items-center gap-2 border-t border-border py-3 md:grid-cols-[12rem_1fr]">
          <div>
            <p className="font-medium">Embeddings</p>
            <p className="text-muted">Not editable here.</p>
          </div>
          <p className="font-mono">
            {s.embed.provider} {s.embed.model}, {s.embed.dims} dimensions
          </p>
        </div>
        <p className="border-t border-border py-3 text-muted">
          Changing the embedding model means embedding every chunk again, so it stays in models.yaml. Edit it there, then
          press Embed again on each document.
        </p>
        {!s.allow_cloud && (
          <p className="pb-3 text-warn">Cloud providers are switched off by egress.allow_cloud in models.yaml.</p>
        )}
        <div className="flex flex-wrap gap-2 pb-3">
          <button className={primary} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            Save choices
          </button>
          <button className={button} disabled={preview.isPending} onClick={() => preview.mutate()}>
            {preview.isPending ? "Running preview" : "Preview on 20 chunks"}
          </button>
        </div>
        {save.isError && <p className="pb-3 text-danger">{(save.error as Error).message}</p>}
        {save.isSuccess && !dirty && <p className="pb-3 text-ok">Saved.</p>}
        {preview.isError && <p className="pb-3 text-danger">{(preview.error as Error).message}</p>}
        {p && (
          <dl className="grid grid-cols-[14rem_1fr] gap-y-1 border-t border-border py-3 font-mono">
            <dt className="text-muted">Chunks sampled</dt>
            <dd>{p.clauses}</dd>
            <dt className="text-muted">Pairs sent to the judge</dt>
            <dd>{p.pairs}</dd>
            <dt className="text-muted">Conflicts / possible</dt>
            <dd>
              {p.conflicts} / {p.possible}
            </dd>
            <dt className="text-muted">Dropped, quote not found</dt>
            <dd>{p.unverified}</dd>
            <dt className="text-muted">Failed calls</dt>
            <dd>{p.failed}</dd>
            <dt className="text-muted">Tokens used</dt>
            <dd>{p.tokens.toLocaleString()}</dd>
            <dt className="text-muted">Full scan of {p.library_chunks} chunks</dt>
            <dd>about {p.full_scan_tokens.toLocaleString()} tokens</dd>
            <dt className="text-muted">Time</dt>
            <dd>{p.seconds} s</dd>
          </dl>
        )}
        {p && dirty && <p className="pb-3 text-muted">This preview used the choices above, which are not saved yet.</p>}
      </section>
    </div>
  );
}
