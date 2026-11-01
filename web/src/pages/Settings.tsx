import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type EmbedPick, type ModelPick, type RerankPick, type SettingsData } from "../api";
import { ModelSelect } from "../components/ModelSelect";
import { PipelineParams, type PipelineValues } from "../components/PipelineParams";
import { button, field, panel, primary } from "../ui";

// The Settings page, for admins. Provider keys, which model each job uses, the search and ranking
// numbers, and a Preview that tries the choices on 20 random chunks before you rely on them. A key
// is tested before it is saved, is stored encrypted, and is never shown again, so the page only
// says whether one is set and where it comes from. Reset puts the search numbers back to defaults.

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

function ModelRow({ label, note, job, value, onChange }: { label: string; note: string; job: "chat" | "vision"; value: ModelPick; onChange: (v: ModelPick) => void }) {
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
        <option value="bedrock">Amazon Bedrock</option>
        <option value="openai_compatible">OpenAI-compatible server</option>
        <option value="ollama">Ollama (local)</option>
      </select>
      <div className="grid gap-2 md:grid-cols-2">
        <ModelSelect
          provider={value.provider}
          job={job}
          baseUrl={value.base_url}
          value={value.model}
          label={label}
          onChange={(model) => onChange({ ...value, model })}
        />
        {(value.provider === "openai_compatible" || value.provider === "ollama") && (
          <input
            className={field}
            value={value.base_url ?? ""}
            aria-label={`${label} server address`}
            placeholder="Server address, for example http://host:8000/v1"
            onChange={(e) => onChange({ ...value, base_url: e.target.value || null })}
          />
        )}
      </div>
    </div>
  );
}

export function Settings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [chat, setChat] = useState<ModelPick | null>(null);
  const [vision, setVision] = useState<ModelPick | null>(null);
  const [rerank, setRerank] = useState<RerankPick | null>(null);
  const [embed, setEmbed] = useState<EmbedPick | null>(null);
  const [pipeline, setPipeline] = useState<PipelineValues | null>(null);

  useEffect(() => {
    if (settings.data) {
      setChat(settings.data.chat);
      setVision(settings.data.vision);
      setRerank(settings.data.rerank);
      setEmbed({ provider: settings.data.embed.provider as EmbedPick["provider"], model: settings.data.embed.model, base_url: settings.data.embed.base_url });
      setPipeline(Object.fromEntries(settings.data.pipeline.map((p) => [p.key, p.value])));
    }
  }, [settings.data]);

  const choices = chat && vision && rerank && embed && pipeline ? { chat, vision, rerank, embed, pipeline } : null;
  const reindex = useMutation({
    mutationFn: api.reindex,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const reset = useMutation({
    mutationFn: api.resetPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const save = useMutation({
    mutationFn: () => api.saveSettings(choices!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const preview = useMutation({ mutationFn: () => api.previewSettings(choices!) });

  if (settings.isError) return <p className="p-6 text-danger">Only an admin can open Settings.</p>;
  if (!settings.data || !choices) return null;
  const s = settings.data;
  const savedEmbed = { provider: s.embed.provider, model: s.embed.model, base_url: s.embed.base_url };
  const embedChanged = embed!.provider !== savedEmbed.provider || embed!.model !== savedEmbed.model;
  const saved = { chat: s.chat, vision: s.vision, rerank: s.rerank, embed: savedEmbed, pipeline: Object.fromEntries(s.pipeline.map((x) => [x.key, x.value])) };
  const dirty = JSON.stringify(choices) !== JSON.stringify(saved);
  const atDefaults = s.pipeline.every((x) => x.value === x.default);
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
        <ModelRow label="Judge and Q&A" note="Reads pairs and answers questions." job="chat" value={chat!} onChange={setChat} />
        <ModelRow label="Figures" note="Reads charts and drawings." job="vision" value={vision!} onChange={setVision} />
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
        <div className="grid items-start gap-2 border-t border-border py-3 md:grid-cols-[12rem_10rem_1fr]">
          <div>
            <p className="font-medium">Embeddings</p>
            <p className="text-muted">Turns each clause into numbers so search can match meaning.</p>
          </div>
          <select
            className={field}
            value={embed!.provider}
            aria-label="Embeddings provider"
            onChange={(e) => setEmbed({ provider: e.target.value as EmbedPick["provider"], model: "", base_url: null })}
          >
            <option value="openai">OpenAI</option>
            <option value="openai_compatible">OpenAI-compatible server</option>
            <option value="ollama">Ollama (local)</option>
          </select>
          <div className="space-y-2">
            <ModelSelect
              provider={embed!.provider}
              job="embed"
              baseUrl={embed!.base_url}
              value={embed!.model}
              label="Embeddings"
              onChange={(model) => setEmbed({ ...embed!, model })}
            />
            {(embed!.provider === "openai_compatible" || embed!.provider === "ollama") && (
              <input
                className={field}
                value={embed!.base_url ?? ""}
                aria-label="Embeddings server address"
                placeholder="Server address, for example http://host:8000/v1"
                onChange={(e) => setEmbed({ ...embed!, base_url: e.target.value || null })}
              />
            )}
            <p className="text-muted">
              Vectors are {s.embed.dims} numbers long, fixed by the database. text-embedding-3-small is the default and is
              cheap. text-embedding-3-large reads wording more finely and costs more per chunk; it is asked for {s.embed.dims}{" "}
              numbers so nothing in the database changes. A hosted model needs no download. A model on Ollama must be pulled
              first, and it must give {s.embed.dims} numbers or it is refused.
            </p>
            {embedChanged && (
              <p className="text-warn">
                Saving a new embedding model means every chunk is embedded again, which sends all your policy text to the
                provider and costs money. Vectors from two models cannot be compared, so search is unreliable until it
                finishes.
              </p>
            )}
          </div>
        </div>
        {s.embed_stale > 0 && !embedChanged && (
          <div className="flex flex-wrap items-center gap-3 border-t border-border py-3">
            <p className="text-warn">
              {s.embed_stale.toLocaleString()} chunks were embedded with another model. Search mixes the two until they are
              embedded again.
            </p>
            <button className={button} disabled={reindex.isPending} onClick={() => reindex.mutate()}>
              {reindex.isPending ? "Queuing" : "Embed all documents again"}
            </button>
            {reindex.isError && <span className="text-danger">{(reindex.error as Error).message}</span>}
          </div>
        )}
        {!s.allow_cloud && (
          <p className="pb-3 text-warn">Cloud providers are switched off by egress.allow_cloud in models.yaml.</p>
        )}
        <h2 className="border-t border-border pt-3 font-medium">Search and ranking</h2>
        <p className="text-muted">
          These numbers decide which clauses are compared with each other. Changes apply to the next scan or question.
          If a stored value is ever invalid, the default is used instead.
        </p>
        <PipelineParams
          params={s.pipeline}
          values={pipeline!}
          onChange={(key, value) => setPipeline({ ...pipeline!, [key]: value })}
        />
        <div className="flex flex-wrap items-center gap-2 border-t border-border py-3">
          <button
            className={button}
            disabled={atDefaults || reset.isPending}
            onClick={() => {
              if (window.confirm("Put every search and ranking number back to its default?")) reset.mutate();
            }}
          >
            Reset to defaults
          </button>
          {reset.isError && <span className="text-danger">{(reset.error as Error).message}</span>}
          {reset.isSuccess && atDefaults && <span className="text-ok">Defaults restored.</span>}
        </div>
        <div className="flex flex-wrap gap-2 pb-3">
          <button
            className={primary}
            disabled={!dirty || save.isPending}
            onClick={() => {
              if (!embedChanged || window.confirm("Embed every chunk again with the new model? This costs money and takes a while.")) save.mutate();
            }}
          >
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
