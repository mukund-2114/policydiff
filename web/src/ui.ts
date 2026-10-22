// Shared class names, so every page uses the same flat controls.
export const field =
  "h-9 w-full rounded-ctl border border-border bg-surface px-3 text-text placeholder:text-muted";
export const button =
  "inline-flex h-9 items-center rounded-ctl border border-border bg-surface px-3 font-medium text-text hover:bg-bg disabled:opacity-50";
export const primary =
  "inline-flex h-9 items-center rounded-ctl bg-accent px-4 font-medium text-accent-text hover:opacity-90 disabled:opacity-50";
export const panel = "rounded-ctl border border-border bg-surface";
export const th = "px-3 py-2 text-left font-medium text-muted";
export const td = "px-3 py-2 align-top";

export function formatDuration(ms: number | null) {
  if (ms === null) return "running";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function versionName(v: { title: string; version_label: string }) {
  return `${v.title} v${v.version_label}`;
}
