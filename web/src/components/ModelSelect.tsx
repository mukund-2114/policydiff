import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { field } from "../ui";

// A model name picker. It asks the api which models the chosen provider offers and shows them in a
// list, so a name cannot be misspelled. When the provider cannot be asked (no key, no list, a server
// that is down) or the admin wants a name that is not listed, it falls back to a typed field.

const CURRENT = "__current__"; // the saved name when the provider does not list it
const TYPE = "__type__"; // switches to the typed field

export function ModelSelect({
  provider,
  job,
  baseUrl,
  value,
  label,
  onChange,
}: {
  provider: string;
  job: "chat" | "vision" | "embed";
  baseUrl?: string | null;
  value: string;
  label: string;
  onChange: (model: string) => void;
}) {
  const [typing, setTyping] = useState(false);
  const list = useQuery({
    queryKey: ["models", provider, job, baseUrl ?? ""],
    queryFn: () => api.models(provider, job, baseUrl),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const models = list.data?.models ?? [];
  const useList = models.length > 0 && !typing;

  if (!useList) {
    return (
      <div>
        <input
          className={field}
          value={value}
          aria-label={`${label} model`}
          placeholder="Model name"
          onChange={(e) => onChange(e.target.value)}
        />
        {list.isFetching && <p className="text-muted">Loading the model list</p>}
        {!list.isFetching && list.data?.message && <p className="text-muted">{list.data.message}</p>}
        {typing && models.length > 0 && (
          <button className="text-accent underline" onClick={() => setTyping(false)}>
            Choose from the list
          </button>
        )}
      </div>
    );
  }
  return (
    <select
      className={field}
      value={models.includes(value) ? value : CURRENT}
      aria-label={`${label} model`}
      onChange={(e) => {
        if (e.target.value === TYPE) setTyping(true);
        else if (e.target.value !== CURRENT) onChange(e.target.value);
      }}
    >
      {!models.includes(value) && <option value={CURRENT}>{value ? `${value} (not in the list)` : "Choose a model"}</option>}
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
      <option value={TYPE}>Type a name instead</option>
    </select>
  );
}
