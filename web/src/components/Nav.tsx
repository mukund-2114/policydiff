import type { ReactNode } from "react";
import type { User } from "../api";
import { button } from "../ui";

// The app frame: a sidebar on wide screens, a compact bar on narrow ones.
// Links are grouped so the daily work (Workspace) is separate from reference material.

type Item = { key: string; label: string; icon: ReactNode };

function Icon({ d }: { d: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const icons = {
  documents: <Icon d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6" />,
  compare: <Icon d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3M16 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3M12 2v20" />,
  samples: <Icon d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14l-4-3H6a2 2 0 0 1-2-2zM8 8h8M8 12h5" />,
  key: <Icon d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />,
  status: <Icon d="M22 12h-4l-3 9L9 3l-3 9H2" />,
};

export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-ctl bg-accent font-semibold text-accent-text"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      aria-hidden="true"
    >
      PD
    </span>
  );
}

function Group({ title, items, page }: { title: string; items: Item[]; page: string }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="px-3 text-xs font-medium uppercase tracking-wide text-muted">{title}</p>
      {items.map((i) => {
        const active = page === i.key || (i.key === "samples" && page === "sample-compare");
        return (
          <a
            key={i.key}
            href={`#/${i.key}`}
            aria-current={active ? "page" : undefined}
            className={`flex h-9 items-center gap-2.5 rounded-ctl px-3 ${
              active
                ? "bg-accent-soft font-medium text-accent"
                : "text-muted hover:bg-bg hover:text-text"
            }`}
          >
            {i.icon}
            {i.label}
          </a>
        );
      })}
    </div>
  );
}

export function Nav({
  productName,
  user,
  page,
  showSamples,
  onSignOut,
}: {
  productName: string;
  user: User;
  page: string;
  showSamples: boolean;
  onSignOut: () => void;
}) {
  const workspace: Item[] = [
    { key: "documents", label: "Documents", icon: icons.documents },
    { key: "compare", label: "Compare", icon: icons.compare },
  ];
  const reference: Item[] = showSamples
    ? [
        { key: "samples", label: "Sample policies", icon: icons.samples },
        { key: "answer-key", label: "Answer key", icon: icons.key },
      ]
    : [];
  const system: Item[] = [{ key: "status", label: "Status", icon: icons.status }];

  return (
    <aside className="flex flex-col gap-5 border-b border-border bg-surface p-3 md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:overflow-y-auto md:border-b-0 md:border-r">
      <a href="#/documents" className="flex items-center gap-2.5 px-1 py-1">
        <BrandMark />
        <span className="text-base font-semibold">{productName}</span>
      </a>
      <nav className="flex flex-col gap-5" aria-label="Main">
        <Group title="Workspace" items={workspace} page={page} />
        <Group title="Reference" items={reference} page={page} />
        <Group title="System" items={system} page={page} />
      </nav>
      <div className="mt-auto space-y-2 border-t border-border pt-3">
        <p className="truncate px-1 text-muted" title={user.email}>
          {user.email}
        </p>
        <button className={`${button} w-full justify-center`} onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
