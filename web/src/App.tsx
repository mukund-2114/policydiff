import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "./api";

const PRODUCT_NAME = "Policy Diff";

const field =
  "h-9 w-full rounded-ctl border border-border bg-surface px-3 text-text placeholder:text-muted";
const button =
  "h-9 rounded-ctl border border-border bg-surface px-3 font-medium text-text hover:bg-bg";
const primary =
  "h-9 rounded-ctl bg-accent px-4 font-medium text-accent-text hover:opacity-90 disabled:opacity-50";

function Login() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess: (user) => qc.setQueryData(["me"], user),
  });

  return (
    <main className="mx-auto mt-24 w-full max-w-sm px-4">
      <h1 className="mb-6 text-xl font-semibold">{PRODUCT_NAME}</h1>
      <form
        className="space-y-4 rounded-ctl border border-border bg-surface p-5"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <label className="block space-y-1">
          <span className="text-muted">Email</span>
          <input
            className={field}
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-muted">Password</span>
          <input
            className={field}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {login.isError && (
          <p role="alert" className="text-danger">
            {login.error instanceof ApiError ? login.error.message : "Sign in failed."}
          </p>
        )}
        <button className={`${primary} w-full`} disabled={login.isPending}>
          Sign in
        </button>
      </form>
    </main>
  );
}

function Home({ email }: { email: string }) {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => qc.setQueryData(["me"], null),
  });
  const h = health.data;

  return (
    <div>
      <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
        <span className="font-semibold">{PRODUCT_NAME}</span>
        <span className="flex items-center gap-3">
          <span className="text-muted">{email}</span>
          <button className={button} onClick={() => logout.mutate()}>
            Sign out
          </button>
        </span>
      </header>
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">
        <section>
          <h2 className="mb-2 font-semibold">Review queue</h2>
          <p className="text-muted">No findings yet. Upload documents to start a scan.</p>
        </section>
        <section>
          <h2 className="mb-2 font-semibold">System status</h2>
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1 rounded-ctl border border-border bg-surface p-4">
            <dt className="text-muted">Overall</dt>
            <dd className="font-mono">{h?.status ?? "checking"}</dd>
            <dt className="text-muted">Database</dt>
            <dd className="font-mono">{h?.db ?? "checking"}</dd>
            <dt className="text-muted">Chat model</dt>
            <dd className="font-mono">{h?.models.chat ?? "not configured"}</dd>
            <dt className="text-muted">Embeddings</dt>
            <dd className="font-mono">{h?.models.embed ?? "not configured"}</dd>
            {h?.models.error && (
              <>
                <dt className="text-muted">Model issue</dt>
                <dd className="text-warn">{h.models.error}</dd>
              </>
            )}
          </dl>
        </section>
      </main>
    </div>
  );
}

export function App() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () =>
      api.me().catch((e) => {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }),
  });
  if (me.isPending) return null;
  return me.data ? <Home email={me.data.email} /> : <Login />;
}
