"use client";

import type { DiscoveredVariable, ZipAnalysis } from "@/lib/api";

export type SelectedDiscoveredVar = DiscoveredVariable & {
  label: string;
  fieldType: "number" | "text" | "select";
  min: string;
  max: string;
};

type Props = {
  analysis: ZipAnalysis;
  selected: Map<string, SelectedDiscoveredVar>;
  onToggleVar: (v: DiscoveredVariable) => void;
  onUpdateVar: (key: string, patch: Partial<SelectedDiscoveredVar>) => void;
  varKey: (v: DiscoveredVariable) => string;
};

export function DiscoveredParametersPicker({
  analysis,
  selected,
  onToggleVar,
  onUpdateVar,
  varKey,
}: Props) {
  const groupedVars: Record<string, DiscoveredVariable[]> = {};
  for (const v of analysis.discovered_variables) {
    (groupedVars[v.file] ??= []).push(v);
  }

  return (
    <>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
        Choose which discovered variables users can adjust when running this simulation.
      </p>

      {analysis.discovered_variables.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--muted)" }}>
          No adjustable variables were discovered in this case. You can still create the simulation
          and add parameters manually later.
        </p>
      ) : (
        Object.entries(groupedVars).map(([file, vars]) => (
          <div key={file} className="var-group">
            <div className="var-group-header">
              <code>{file}</code>
              <span className="var-group-count">{vars.length} variables</span>
            </div>
            <div className="var-group-list">
              {vars.map((v) => {
                const k = varKey(v);
                const isSelected = selected.has(k);
                const sel = selected.get(k);
                return (
                  <div key={k} className={`var-row ${isSelected ? "selected" : ""}`}>
                    <div className="var-row-main">
                      <label className="var-check">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => onToggleVar(v)}
                        />
                        <code className="var-key">{v.key}</code>
                      </label>
                      <span className="var-value">{v.value}</span>
                      <span className="badge">{v.type}</span>
                    </div>
                    {isSelected && sel && (
                      <div className="var-config">
                        <div className="var-config-field">
                          <label>Display Label</label>
                          <input
                            type="text"
                            value={sel.label}
                            onChange={(e) => onUpdateVar(k, { label: e.target.value })}
                          />
                        </div>
                        <div className="var-config-field">
                          <label>Type</label>
                          <select
                            value={sel.fieldType}
                            onChange={(e) =>
                              onUpdateVar(k, {
                                fieldType: e.target.value as "number" | "text",
                              })
                            }
                          >
                            <option value="number">Number</option>
                            <option value="text">Text</option>
                          </select>
                        </div>
                        {sel.fieldType === "number" && (
                          <>
                            <div className="var-config-field">
                              <label>Min</label>
                              <input
                                type="text"
                                placeholder="—"
                                value={sel.min}
                                onChange={(e) => onUpdateVar(k, { min: e.target.value })}
                              />
                            </div>
                            <div className="var-config-field">
                              <label>Max</label>
                              <input
                                type="text"
                                placeholder="—"
                                value={sel.max}
                                onChange={(e) => onUpdateVar(k, { max: e.target.value })}
                              />
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </>
  );
}
