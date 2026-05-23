"use client";

import { useMemo, useState } from "react";
import type { MassRunPreviewRun, SimulationInputField } from "@/lib/api";

function reindexRuns(runs: MassRunPreviewRun[]): MassRunPreviewRun[] {
  return runs.map((run, index) => ({ ...run, index }));
}

type Props = {
  fieldLabels: string[];
  inputFields: SimulationInputField[];
  runs: MassRunPreviewRun[];
  batchSize: number;
  starting: boolean;
  onRunsChange: (runs: MassRunPreviewRun[]) => void;
  onStart: () => void;
};

export function MassRunPreviewEditor({
  fieldLabels,
  inputFields,
  runs,
  batchSize,
  starting,
  onRunsChange,
  onStart,
}: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const fieldTypes = useMemo(() => {
    const m = new Map<string, SimulationInputField["type"]>();
    for (const f of inputFields) {
      m.set(f.label, f.type);
    }
    return m;
  }, [inputFields]);

  const allSelected = runs.length > 0 && selected.size === runs.length;
  const someSelected = selected.size > 0 && !allSelected;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(runs.map((r) => r.index)));
    }
  };

  const toggleRow = (index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const updateValue = (runIndex: number, label: string, value: string) => {
    onRunsChange(
      runs.map((run) => {
        if (run.index !== runIndex) return run;
        return {
          ...run,
          inputs: run.inputs.map((inp) =>
            inp.label === label ? { ...inp, value } : inp,
          ),
        };
      }),
    );
  };

  const removeRow = (runIndex: number) => {
    onRunsChange(reindexRuns(runs.filter((r) => r.index !== runIndex)));
    setSelected(new Set());
  };

  const deleteSelected = () => {
    if (selected.size === 0) return;
    const next = reindexRuns(runs.filter((r) => !selected.has(r.index)));
    onRunsChange(next);
    setSelected(new Set());
  };

  const count = runs.length;

  return (
    <section className="panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="section-title" style={{ margin: 0 }}>Preview</div>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          {count} simulation{count === 1 ? "" : "s"} · batch size {batchSize}
        </span>
      </div>

      {fieldLabels.length > 0 && (
        <p style={{ fontSize: 13, margin: "0 0 12px", color: "var(--text-secondary)" }}>
          Edit values below or remove rows before starting. Input columns: {fieldLabels.join(", ")}
        </p>
      )}

      {selected.size > 0 && (
        <div className="mass-run-toolbar row gap-sm" style={{ marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {selected.size} selected
          </span>
          <button type="button" className="secondary sm danger" onClick={deleteSelected}>
            Delete selected
          </button>
          <button type="button" className="secondary sm" onClick={() => setSelected(new Set())}>
            Clear selection
          </button>
        </div>
      )}

      <div className="mass-run-table-wrap">
        <table className="mass-run-table mass-run-table-editable">
          <thead>
            <tr>
              <th className="mass-run-col-check">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected;
                  }}
                  onChange={toggleSelectAll}
                  aria-label="Select all rows"
                />
              </th>
              <th>#</th>
              {fieldLabels.map((lab) => (
                <th key={lab}>{lab}</th>
              ))}
              <th className="mass-run-col-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td colSpan={fieldLabels.length + 3} style={{ color: "var(--muted)", fontSize: 13 }}>
                  No runs left. Upload a CSV again or add rows from a new preview.
                </td>
              </tr>
            ) : (
              runs.map((run) => (
                <tr key={run.index} className={selected.has(run.index) ? "mass-run-row-selected" : undefined}>
                  <td className="mass-run-col-check">
                    <input
                      type="checkbox"
                      checked={selected.has(run.index)}
                      onChange={() => toggleRow(run.index)}
                      aria-label={`Select run ${run.index + 1}`}
                    />
                  </td>
                  <td>{run.index + 1}</td>
                  {fieldLabels.map((lab) => {
                    const inp = run.inputs.find((i) => i.label === lab);
                    const val = inp?.value ?? "";
                    const ftype = fieldTypes.get(lab) ?? "text";
                    return (
                      <td key={lab}>
                        <input
                          className="mass-run-cell-input"
                          type={ftype === "number" ? "number" : "text"}
                          value={val}
                          onChange={(e) => updateValue(run.index, lab, e.target.value)}
                        />
                      </td>
                    );
                  })}
                  <td className="mass-run-col-actions">
                    <button
                      type="button"
                      className="secondary sm"
                      onClick={() => removeRow(run.index)}
                      aria-label={`Remove run ${run.index + 1}`}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="row gap-sm" style={{ marginTop: 20 }}>
        <button
          type="button"
          disabled={starting || count === 0}
          onClick={onStart}
        >
          {starting ? "Starting…" : `Start Mass Run (${count} runs)`}
        </button>
      </div>
    </section>
  );
}
