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
  status: string; // queued, parsing, parsed, failed
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
  upload: (form: FormData) => request<UploadResult>("/documents/upload", { method: "POST", body: form }),
  fileUrl: (id: string) => `/api/versions/${id}/file`,

  samplesAvailable: () =>
    request<{ available: boolean }>("/samples/northwind").then((r) => r.available, () => false),
  samplePolicies: () => request<SamplePolicy[]>("/samples/northwind/policies"),
  samplePolicy: (id: string) => request<SamplePolicyFull>(`/samples/northwind/policies/${id}`),
  answerKey: () => request<AnswerKey>("/samples/northwind/answer-key"),
};
