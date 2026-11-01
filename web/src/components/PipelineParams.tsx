import { type PipelineParam } from "../api";
import { field } from "../ui";

// The search and ranking numbers on the Settings page. The rows are drawn from what the api sends
// (name, range, default, and what raising or lowering the number does), so a number added on the
// server shows up here without a change to this file. A number moved in the direction that costs
// more gets a warning line, so an admin sees the cost before saving.

export type PipelineValues = Record<string, number | string>;

function costs(p: PipelineParam, value: number | string) {
  if (p.cost === null) return false;
  if (p.options) return value !== p.default; // a choice costs more or less than the default, not "higher"
  return p.cost_up ? value > p.default : value < p.default;
}

export function PipelineParams({
  params,
  values,
  onChange,
}: {
  params: PipelineParam[];
  values: PipelineValues;
  onChange: (key: string, value: number | string) => void;
}) {
  const groups = [...new Set(params.map((p) => p.group))];
  return (
    <div>
      {groups.map((group) => (
        <div key={group}>
          <h3 className="pt-3 text-muted">{group}</h3>
          {params
            .filter((p) => p.group === group)
            .map((p) => {
              const value = values[p.key] ?? p.value;
              return (
                <div key={p.key} className="grid gap-2 border-t border-border py-3 first:border-t-0 md:grid-cols-[14rem_1fr]">
                  <div>
                    <label className="font-medium" htmlFor={`param-${p.key}`}>
                      {p.label}
                    </label>
                    <p className="font-mono text-muted">Default {p.default}</p>
                    {p.options ? (
                      <select
                        id={`param-${p.key}`}
                        className={`${field} mt-1 max-w-[10rem]`}
                        value={value}
                        onChange={(e) => onChange(p.key, e.target.value)}
                      >
                        {p.options.map((o) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`param-${p.key}`}
                        className={`${field} mt-1 max-w-[8rem] font-mono`}
                        type="number"
                        min={p.low}
                        max={p.high}
                        step={p.step}
                        value={value}
                        onChange={(e) => onChange(p.key, Number(e.target.value))}
                      />
                    )}
                  </div>
                  <div className="space-y-1">
                    <p>
                      {!p.options && <span className="text-muted">Higher: </span>}
                      {p.more}
                    </p>
                    <p>
                      {!p.options && <span className="text-muted">Lower: </span>}
                      {p.less}
                    </p>
                    {p.unlock && <p className="text-muted">{p.unlock}</p>}
                    {p.cost && (
                      <p className={costs(p, value) ? "text-warn" : "text-muted"}>
                        {costs(p, value) ? "This setting is now costing more than the default. " : "Cost: "}
                        {p.cost}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      ))}
    </div>
  );
}
