import { useSyncExternalStore } from "react";

// A very small router that keeps the page in the URL hash: #/documents/123 or #/compare?a=1&b=2.
// Hash links need no server setup and can be copied and shared. TanStack Router can replace this later.

function subscribe(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

const read = () => window.location.hash.replace(/^#/, "") || "/documents";

export function useRoute(): { path: string[]; query: URLSearchParams } {
  const hash = useSyncExternalStore(subscribe, read);
  const [path, search = ""] = hash.split("?");
  return { path: path.split("/").filter(Boolean), query: new URLSearchParams(search) };
}

export function compareHref(a?: string | null, b?: string | null) {
  const q = new URLSearchParams();
  if (a) q.set("a", a);
  if (b) q.set("b", b);
  return `#/compare?${q.toString()}`;
}

export function go(href: string) {
  window.location.hash = href.replace(/^#/, "");
}
