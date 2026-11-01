export type User = { id: string; email: string; role: string };

export type Health = {
  status: "ok" | "degraded" | "down";
  db: string;
  pgvector: string;
  models: { chat?: string; embed?: string; allow_cloud?: boolean; error?: string };
};

export type Version = {
  id: string;
  document_id: string;
  title: string;
  collection: string;
  owner_team: string | null;
  version_label: string;
  effective_from: string | null;
  effective_to: string | null;
  status: string; // queued, parsing, parsed, chunking, chunked, embedding, ready, superseded, failed
  failed_stage: string | null;
  created_at: string;
  pages: number | null;
};

export type Stage = {
  stage: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  detail: Record<string, number | string> | null;
  error: string | null;
};

export type SearchHit = {
  chunk_id: string;
  version_id: string;
  title: string;
  version_label: string;
  heading_path: string | null;
  page: number | null;
  text: string;
  score: number;
  vector_rank: number | null;
  keyword_rank: number | null;
  rerank_score: number;
  kept: boolean;
};

export type Scan = {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  started_at: string | null;
  finished_at: string | null;
  judge_calls: number;
  tokens: number;
  stats: Record<string, number> | null;
  progress: { clause: number; of: number } | null;
  error: string | null;
  settings: Record<string, string | number>;
};

export type FindingSide = {
  version_id: string;
  boxes: { page: number; bbox: number[] }[];
  kind: "text" | "table" | "figure";
  summary: string | null;
  facts: { kind: string; subject: string; value: string }[];
  title: string; version_label: string; heading_path: string | null; page: number | null };

export type Finding = {
  id: string;
  type: string;
  status: string;
  confidence: number;
  explanation: string;
  quote_a: string;
  quote_b: string;
  owner: string | null;
  resolution_note: string | null;
  a: FindingSide;
  b: FindingSide;
  scores: Record<string, number | string | boolean | null>;
};

export type Chunk = {
  position: number;
  kind: "text" | "table" | "figure";
  heading_path: string | null;
  text: string;
  context_header: string | null;
  page: number | null;
  summary: string | null;
  facts: { items: { kind: string; subject: string; value: string }[] } | null;
  embedding_model: string | null;
};

export type VersionDetail = Version & { stages: Stage[] };

export type ParsedBlock = { text: string; size: number; bold: boolean; bbox: number[] };
export type ParsedPage = {
  number: number;
  blocks: ParsedBlock[];
  tables: { bbox: number[]; rows: string[][] }[];
  images: number;
};

export type UploadResult = { version: Version; duplicate: boolean };

export type SamplePolicy = {
  doc_id: string;
  title: string;
  version: string;
  effective: string;
  owner: string;
  collection: string;
};
export type SamplePolicyFull = SamplePolicy & { markdown: string };

export type AnswerSide = {
  doc: string;
  title: string;
  ref: string;
  kind: "clause" | "table" | "figure";
  text: string;
};
export type AnswerItem = {
  id: string;
  note: string;
  type?: string;
  modality?: "text" | "table" | "figure";
  a: AnswerSide;
  b: AnswerSide;
};
export type AnswerKey = { conflicts: AnswerItem[]; near_misses: AnswerItem[] };

export type ModelPick = {
  provider: "openai" | "openai_compatible" | "anthropic" | "bedrock" | "ollama";
  model: string;
  base_url?: string | null;
};
export type EmbedPick = { provider: "openai" | "openai_compatible" | "ollama"; model: string; base_url?: string | null };
export type RerankPick = { provider: "local" | "llm" | "cohere"; model: string | null };
export type PipelineParam = {
  key: string;
  label: string;
  group: string;
  low: number;
  high: number;
  step: number;
  default: number | string;
  value: number | string;
  options: string[] | null; // set for a choice from a list instead of a number
  unlock: string | null; // what to do before a change takes effect, for example cut documents again
  more: string; // what happens when it goes up
  less: string; // what happens when it goes down
  cost: string | null; // set when changing it changes the cost
  cost_up: boolean; // true: a higher value costs more
};
export type SettingsData = {
  chat: ModelPick;
  vision: ModelPick;
  rerank: RerankPick;
  pipeline: PipelineParam[];
  embed: { provider: string; model: string; dims: number; base_url: string | null };
  embed_stale: number; // chunks still embedded with another model than the one chosen
  keys: Record<string, { set: boolean; source: "settings" | "env" | null }>;
  allow_cloud: boolean;
};
export type SettingsChoices = Partial<Pick<SettingsData, "chat" | "vision" | "rerank">> & {
  embed?: EmbedPick;
  pipeline?: Record<string, number | string>;
};
export type PreviewResult = {
  clauses: number;
  pairs: number;
  conflicts: number;
  possible: number;
  unverified: number;
  failed: number;
  tokens: number;
  library_chunks: number;
  full_scan_tokens: number;
  seconds: number;
};

export type AuditEvent = {
  id: string;
  at: string;
  user: string | null;
  action: string;
  target: string | null;
  detail: Record<string, unknown> | null;
};

export type AskPassage = {
  n: number;
  chunk_id: string;
  version_id: string;
  title: string;
  version_label: string;
  heading_path: string | null;
  page: number | null;
  kind: string;
  text: string;
};
export type AskFinding = {
  id: string;
  type: string;
  status: string;
  confidence: number;
  explanation: string;
  between: string;
};
// What the chat endpoint sends, one event at a time: the passages found, then pieces of the answer,
// then a closing summary (or an error).
export type AskEvent =
  | { type: "passages"; passages: AskPassage[]; rewrites?: string[] }
  | { type: "token"; text: string }
  | { type: "done"; cited: number[]; findings: AskFinding[]; tokens: number; seconds: number }
  | { type: "error"; message: string };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // A string body is JSON. A FormData body (file upload) sets its own content type.
  const headers: HeadersInit = typeof init.body === "string" ? { "Content-Type": "application/json" } : {};
  const res = await fetch(`/api${path}`, { credentials: "same-origin", headers, ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  health: () => request<Health>("/health"),

  documents: () => request<Version[]>("/documents"),
  version: (id: string) => request<VersionDetail>(`/versions/${id}`),
  parsed: (id: string) => request<{ pages: ParsedPage[] }>(`/versions/${id}/parsed`),
  chunks: (id: string) => request<Chunk[]>(`/versions/${id}/chunks`),
  rechunk: (id: string) => request<{ queued: boolean }>(`/versions/${id}/chunk`, { method: "POST" }),
  reembed: (id: string) => request<{ queued: boolean }>(`/versions/${id}/embed`, { method: "POST" }),
  remove: (id: string) => request<void>(`/versions/${id}`, { method: "DELETE" }),
  reparse: (id: string) => request<{ queued: boolean }>(`/versions/${id}/parse`, { method: "POST" }),
  upload: (form: FormData) => request<UploadResult>("/documents/upload", { method: "POST", body: form }),
  search: (query: string) =>
    request<SearchHit[]>("/search", { method: "POST", body: JSON.stringify({ query }) }),
  related: (chunkId: string) => request<SearchHit[]>(`/chunks/${chunkId}/related`),
  startScan: (id: string) => request<Scan>(`/versions/${id}/scan`, { method: "POST" }),
  scans: (id: string) => request<Scan[]>(`/versions/${id}/scans`),
  findings: () => request<Finding[]>("/findings"),
  updateFinding: (id: string, changes: Partial<Pick<Finding, "status" | "owner" | "resolution_note">>) =>
    request<Finding>(`/findings/${id}`, { method: "PATCH", body: JSON.stringify(changes) }),
  audit: (action: string, limit: number, offset: number) =>
    request<AuditEvent[]>(`/audit?limit=${limit}&offset=${offset}${action ? `&action=${encodeURIComponent(action)}` : ""}`),
  settings: () => request<SettingsData>("/settings"),
  saveSettings: (body: SettingsChoices & { keys?: Record<string, string | null> }) =>
    request<SettingsData>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  reindex: () => request<SettingsData>("/settings/embed/reindex", { method: "POST" }),
  models: (provider: string, job: string, baseUrl?: string | null) =>
    request<{ models: string[]; message: string | null }>(
      `/settings/models?provider=${provider}&job=${job}${baseUrl ? `&base_url=${encodeURIComponent(baseUrl)}` : ""}`,
    ),
  resetPipeline: () => request<SettingsData>("/settings/pipeline/reset", { method: "POST" }),
  testKey: (provider: string, key?: string) =>
    request<{ ok: boolean; message: string }>("/settings/test-key", {
      method: "POST",
      body: JSON.stringify({ provider, key: key ?? null }),
    }),
  previewSettings: (body: SettingsChoices) =>
    request<PreviewResult>("/settings/preview", { method: "POST", body: JSON.stringify(body) }),
  fileUrl: (id: string) => `/api/versions/${id}/file`,

  samplesAvailable: () =>
    request<{ available: boolean }>("/samples/northwind").then((r) => r.available, () => false),
  loadSamples: () =>
    request<{ added: number; already_there: number; missing: string[] }>("/samples/northwind/load", {
      method: "POST",
    }),
  samplePolicies: () => request<SamplePolicy[]>("/samples/northwind/policies"),
  samplePolicy: (id: string) => request<SamplePolicyFull>(`/samples/northwind/policies/${id}`),
  answerKey: () => request<AnswerKey>("/samples/northwind/answer-key"),
};

// Reads the chat answer as it arrives. The server sends "data: {json}" blocks separated by a blank line.
export async function* askStream(body: {
  question: string;
  history: { role: string; content: string }[];
  as_of: string | null;
}): AsyncGenerator<AskEvent> {
  const res = await fetch("/api/ask/stream", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof detail.detail === "string" ? detail.detail : res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (block.startsWith("data: ")) yield JSON.parse(block.slice(6)) as AskEvent;
    }
  }
}
