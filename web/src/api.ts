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
export type RerankPick = { provider: "local" | "llm" | "cohere"; model: string | null };
export type SettingsData = {
  chat: ModelPick;
  vision: ModelPick;
  rerank: RerankPick;
  embed: { provider: string; model: string; dims: number };
  keys: Record<string, { set: boolean; source: "settings" | "env" | null }>;
  allow_cloud: boolean;
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

export type AskResult = {
  answer: string;
  tokens: number;
  passages: {
    n: number;
    chunk_id: string;
    version_id: string;
    title: string;
    version_label: string;
    heading_path: string | null;
    page: number | null;
    kind: string;
    text: string;
    cited: boolean;
  }[];
  findings: { id: string; type: string; status: string; confidence: number; explanation: string; between: string }[];
};

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
  saveSettings: (body: Partial<Pick<SettingsData, "chat" | "vision" | "rerank">> & { keys?: Record<string, string | null> }) =>
    request<SettingsData>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  testKey: (provider: string, key?: string) =>
    request<{ ok: boolean; message: string }>("/settings/test-key", {
      method: "POST",
      body: JSON.stringify({ provider, key: key ?? null }),
    }),
  previewSettings: (body: Partial<Pick<SettingsData, "chat" | "vision" | "rerank">>) =>
    request<PreviewResult>("/settings/preview", { method: "POST", body: JSON.stringify(body) }),
  ask: (question: string, asOf: string | null) =>
    request<AskResult>("/ask", { method: "POST", body: JSON.stringify({ question, as_of: asOf }) }),
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
