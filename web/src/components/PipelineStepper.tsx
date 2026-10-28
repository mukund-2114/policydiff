import { useState } from "react";
import type { Stage, VersionDetail } from "../api";
import { formatDuration, panel } from "../ui";

type Tab = "chunks" | "parsed";

// One entry per step of the pipeline. "stage" matches the name the worker records, so a step is
// drawn from the real stage rows and never from a guess. Steps with no stage name are fixed.
type Step = { key: string; label: string; stage?: string; does: string; tab?: Tab; later?: boolean };

const STEPS: Step[] = [
  {
    key: "upload",
    label: "Upload",
    does: "Checks the file is a PDF, stores it, and skips it if the same file was uploaded before.",
  },
  {
    key: "parsing",
    label: "Parsing",
    stage: "parsing",
    tab: "parsed",
    does: "Reads every page and saves what it sees: text blocks with font size and bold, tables, and where the images are.",
  },
  {
    key: "chunking",
    label: "Chunking",
    stage: "chunking",
    tab: "chunks",
    does: "Finds the headings, cuts the text into numbered clauses, and turns each table and picture into its own chunk.",
  },
  {
    key: "headers",
    label: "Context headers",
    stage: "headers",
    tab: "chunks",
    does: "Writes one line for each chunk (document, version, date, section) that goes in front of the text before it is embedded.",
  },
  {
    key: "enriching",
    label: "Summaries and facts",
    stage: "enriching",
    tab: "chunks",
    does: "Asks the model to describe each table and figure, so they can be searched, and to list the numbers, durations and obligations in each chunk for the judge.",
  },
  {
    key: "embedding",
    label: "Embedding",
    stage: "embedding",
    tab: "chunks",
    does: "Sends each chunk (context line plus text) to the embedding model for a vector, and builds a keyword index from the same text.",
  },
];

type State = "done" | "running" | "failed" | "waiting" | "later";

const STATE_TEXT: Record<State, string> = {
  done: "Done",
  running: "In progress",
  failed: "Failed",
  waiting: "Waiting",
  later: "Not built yet",
};

function latest(stages: Stage[], name?: string) {
  return stages.filter((s) => s.stage === name).at(-1);
}

function stateOf(step: Step, stages: Stage[]): State {
  if (step.key === "upload") return "done";
  if (step.later) return "later";
  return latest(stages, step.stage)?.status ?? "waiting";
}

function Dot({ state, n }: { state: State; n: number }) {
  const base = "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 font-mono";
  if (state === "done")
    return (
      <span className={`${base} border-accent bg-accent text-accent-text`} aria-hidden>
        ✓
      </span>
    );
  if (state === "running")
    return (
      <span className={`${base} animate-pulse border-accent bg-accent-soft text-accent`} aria-hidden>
        {n}
      </span>
    );
  if (state === "failed")
    return (
      <span className={`${base} border-danger text-danger`} aria-hidden>
        !
      </span>
    );
  return (
    <span className={`${base} border-border text-muted ${state === "later" ? "border-dashed" : ""}`} aria-hidden>
      {n}
    </span>
  );
}

function Detail({
  step,
  stage,
  state,
  onOpenTab,
}: {
  step: Step;
  stage?: Stage;
  state: State;
  onOpenTab: (t: Tab) => void;
}) {
  const tab = step.tab;
  return (
    <div className={`${panel} space-y-2 px-4 py-3`}>
      <p className="flex items-baseline gap-3">
        <span className="font-medium">{step.label}</span>
        <span className={`font-mono ${state === "failed" ? "text-danger" : "text-muted"}`}>{STATE_TEXT[state]}</span>
        {stage && <span className="ml-auto font-mono text-muted">{formatDuration(stage.duration_ms)}</span>}
      </p>
      <p>{step.does}</p>
      {stage?.detail && (
        <dl className="grid grid-cols-[10rem_1fr] gap-y-0.5 font-mono">
          {Object.entries(stage.detail).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
              <dd className="break-words">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {stage?.error && <p className="font-mono text-danger">{stage.error}</p>}
      {tab && state === "done" && (
        <button className="text-accent hover:underline" onClick={() => onOpenTab(tab)}>
          {tab === "chunks" ? "See the chunks" : "See the parser output"}
        </button>
      )}
    </div>
  );
}

export function PipelineStepper({ v, onOpenTab }: { v: VersionDetail; onOpenTab: (t: Tab) => void }) {
  const [picked, setPicked] = useState<string | null>(null);
  const states = STEPS.map((s) => stateOf(s, v.stages));
  // With nothing picked, follow the work: the running step, else the failed one, else the last done.
  const running = states.indexOf("running");
  const failed = states.indexOf("failed");
  const auto = running >= 0 ? running : failed >= 0 ? failed : states.lastIndexOf("done");
  const open = picked ? STEPS.findIndex((s) => s.key === picked) : auto;
  const step = STEPS[open];

  return (
    <div className="space-y-3" aria-label="Processing steps">
      <ol className="flex items-start">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex flex-1 items-start last:flex-none">
            <button
              className={`flex w-24 flex-col items-center gap-1 rounded-ctl px-1 py-1 text-center ${open === i ? "bg-accent-soft" : "hover:bg-bg"}`}
              onClick={() => setPicked(picked === s.key ? null : s.key)}
              aria-current={open === i ? "step" : undefined}
            >
              <Dot state={states[i]} n={i + 1} />
              <span className="font-medium leading-tight">{s.label}</span>
              <span className={states[i] === "failed" ? "text-danger" : "text-muted"}>{STATE_TEXT[states[i]]}</span>
            </button>
            {i < STEPS.length - 1 && (
              <span
                className={`mt-4 h-0.5 flex-1 ${states[i] === "done" && states[i + 1] !== "later" ? "bg-accent" : "bg-border"}`}
                aria-hidden
              />
            )}
          </li>
        ))}
      </ol>
      {step && <Detail step={step} stage={latest(v.stages, step.stage)} state={states[open]} onOpenTab={onOpenTab} />}
    </div>
  );
}
