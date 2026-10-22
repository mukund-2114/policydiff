import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type User } from "./api";
import { Nav, BrandMark } from "./components/Nav";
import { AnswerKey } from "./pages/AnswerKey";
import { Compare } from "./pages/Compare";
import { DocumentDetail } from "./pages/DocumentDetail";
import { Documents } from "./pages/Documents";
import { SampleCompare } from "./pages/SampleCompare";
import { SampleViewer } from "./pages/SampleViewer";
import { Samples } from "./pages/Samples";
import { Status } from "./pages/Status";
import { useRoute } from "./router";
import { field, primary } from "./ui";

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
      <div className="mb-6 flex items-center gap-3">
        <BrandMark size={36} />
        <div>
          <h1 className="text-xl font-semibold leading-tight">{PRODUCT_NAME}</h1>
          <p className="text-muted">Find conflicts between your policies.</p>
        </div>
      </div>
      <form
        className="space-y-4 rounded-ctl border border-border bg-surface p-6"
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

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Nav
        productName={PRODUCT_NAME}
        user={user}
        page={page}
        showSamples={Boolean(samples.data)}
        onSignOut={() => logout.mutate()}
      />
      <div className="min-w-0 flex-1">
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
