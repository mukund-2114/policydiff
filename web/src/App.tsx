import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type User } from "./api";
import { AnswerKey } from "./pages/AnswerKey";
import { Compare } from "./pages/Compare";
import { DocumentDetail } from "./pages/DocumentDetail";
import { Documents } from "./pages/Documents";
import { SampleCompare } from "./pages/SampleCompare";
import { SampleViewer } from "./pages/SampleViewer";
import { Samples } from "./pages/Samples";
import { Status } from "./pages/Status";
import { useRoute } from "./router";
import { button, field, primary } from "./ui";

const PRODUCT_NAME = "Policy Diff";

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

function Shell({ user }: { user: User }) {
  const qc = useQueryClient();
  const { path } = useRoute();
  const page = path[0] ?? "documents";
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samplesAvailable });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => qc.setQueryData(["me"], null),
  });

  const links = [
    ["documents", "Documents"],
    ["compare", "Compare"],
    ...(samples.data
      ? [
          ["samples", "Sample policies"],
          ["answer-key", "Answer key"],
        ]
      : []),
    ["status", "Status"],
  ];

  return (
    <div>
      <header className="flex h-12 items-center gap-6 border-b border-border bg-surface px-4">
        <span className="font-semibold">{PRODUCT_NAME}</span>
        <nav className="flex h-full gap-4">
          {links.map(([key, label]) => (
            <a
              key={key}
              href={`#/${key}`}
              className={`flex items-center border-b-2 px-1 ${
                (page === key || (key === "samples" && page === "sample-compare")) ? "border-accent font-medium text-text" : "border-transparent text-muted hover:text-text"
              }`}
            >
              {label}
            </a>
          ))}
        </nav>
        <span className="ml-auto flex items-center gap-3">
          <span className="text-muted">{user.email}</span>
          <button className={button} onClick={() => logout.mutate()}>
            Sign out
          </button>
        </span>
      </header>
      {page === "documents" && path[1] ? (
        <DocumentDetail id={path[1]} />
      ) : page === "samples" && path[1] ? (
        <SampleViewer id={path[1]} />
      ) : page === "samples" ? (
        <Samples />
      ) : page === "sample-compare" ? (
        <SampleCompare />
      ) : page === "compare" ? (
        <Compare />
      ) : page === "answer-key" ? (
        <AnswerKey />
      ) : page === "status" ? (
        <Status />
      ) : (
        <Documents user={user} />
      )}
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
  return me.data ? <Shell user={me.data} /> : <Login />;
}
