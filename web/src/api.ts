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

export type FindingSide = { title: string; version_label: string; heading_path: string | null; page: number | null };

export type Finding = {
  id: string;
  type: string;
  status: string;
  confidence: number;
  explanation: string;
  quote_a: string;
  quote_b: string;
  owner: string | null;
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
  fileUrl: (id: string) => `/api/versions/${id}/file`,

  samplesAvailable: () =>
    request<{ available: boolean }>("/samples/northwind").then((r) => r.available, () => false),
  samplePolicies: () => request<SamplePolicy[]>("/samples/northwind/policies"),
  samplePolicy: (id: string) => request<SamplePolicyFull>(`/samples/northwind/policies/${id}`),
  answerKey: () => request<AnswerKey>("/samples/northwind/answer-key"),
};
