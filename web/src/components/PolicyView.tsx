import { Children, isValidElement, useEffect, useRef, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AnswerSide } from "../api";

// Shows one sample policy (Markdown) and highlights the sentences the answer key points at.

const norm = (s: string) => s.replace(/[|\s]+/g, " ").trim().toLowerCase();

function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

export function PolicyView({ markdown, marks }: { markdown: string; marks: AnswerSide[] }) {
  const box = useRef<HTMLDivElement>(null);

  // A clause or table row is marked when it contains the quote. A figure is marked by its caption.
  const hit = (text: string) =>
    marks.some((m) => (m.kind === "figure" ? norm(text).startsWith(norm(m.ref)) : norm(text).includes(norm(m.text))));
  const mark = (on: boolean) => (on ? { "data-hit": "true", className: "my-2 -mx-2 rounded-ctl bg-warn/20 px-2 py-1" } : { className: "my-2" });

  const components: Components = {
    h1: ({ children }) => <h1 className="mb-3 text-xl font-semibold">{children}</h1>,
    h2: ({ children }) => <h2 className="mb-1 mt-6 text-[15px] font-semibold">{children}</h2>,
    h3: ({ children }) => <h3 className="mb-1 mt-4 font-semibold">{children}</h3>,
    p: ({ children }) => <p {...mark(hit(textOf(children)))}>{children}</p>,
    table: ({ children }) => <table className="my-2 border-collapse">{children}</table>,
    th: ({ children }) => <th className="border border-border bg-bg px-3 py-1 text-left font-medium">{children}</th>,
    td: ({ children }) => <td className="border border-border px-3 py-1">{children}</td>,
    tr: ({ children }) => {
      const on = hit(Children.toArray(children).map(textOf).join(" "));
      return <tr {...(on ? { "data-hit": "true", className: "bg-warn/20" } : {})}>{children}</tr>;
    },
    img: ({ src, alt }) => (
      <img
        alt={alt}
        src={src?.replace(/^figures\//, "/api/samples/northwind/figures/")}
        className="my-2 max-w-full rounded-ctl border border-border bg-white"
      />
    ),
  };

  // Scroll the first marked sentence into view when the document or the marks change.
  const key = marks.map((m) => m.text).join("|");
  useEffect(() => {
    box.current?.querySelector("[data-hit]")?.scrollIntoView({ block: "center" });
  }, [markdown, key]);

  return (
    <div ref={box}>
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {markdown}
      </Markdown>
    </div>
  );
}
