"use client";

import type { SimulationInputField } from "@/lib/api";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";

type Props = {
  fields: SimulationInputField[];
  onChange: (fields: SimulationInputField[]) => void;
};

export function SimulationInputFieldsEditor({ fields, onChange }: Props) {
  const updateField = (idx: number, patch: Partial<SimulationInputField>) => {
    onChange(fields.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  };

  const removeField = (idx: number) => {
    onChange(fields.filter((_, i) => i !== idx));
  };

  const addField = () => {
    onChange([...fields, { key: "", label: "", type: "text", default: "" }]);
  };

  return (
    <>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
        These parameters will be shown to users when they run this simulation.
      </p>

      {fields.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 12px" }}>
          No parameters defined.
        </p>
      ) : (
        <div className="edit-params-list">
          {fields.map((f, i) => (
            <div key={i} className="edit-param-row">
              <div className="edit-param-fields">
                <div className="var-config-field">
                  <label>Key</label>
                  <input
                    type="text"
                    value={f.key}
                    onChange={(e) => updateField(i, { key: e.target.value })}
                    placeholder="e.g. system/controlDict::endTime"
                    style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}
                  />
                </div>
                <div className="var-config-field">
                  <label>Label</label>
                  <input
                    type="text"
                    value={f.label}
                    onChange={(e) => updateField(i, { label: e.target.value })}
                    placeholder="Display label"
                  />
                </div>
                <div className="var-config-field">
                  <label>Type</label>
                  <ForgeSelect
                    value={f.type}
                    onChange={(v) =>
                      updateField(i, {
                        type: v as "number" | "text" | "select",
                      })
                    }
                    options={[
                      { value: "number", label: "Number" },
                      { value: "text", label: "Text" },
                      { value: "select", label: "Select" },
                    ]}
                    aria-label="Field type"
                  />
                </div>
                <div className="var-config-field">
                  <label>Default</label>
                  <input
                    type="text"
                    value={f.default}
                    onChange={(e) => updateField(i, { default: e.target.value })}
                  />
                </div>
                {f.type === "number" && (
                  <>
                    <div className="var-config-field">
                      <label>Min</label>
                      <input
                        type="text"
                        placeholder="—"
                        value={f.min ?? ""}
                        onChange={(e) => updateField(i, { min: e.target.value })}
                      />
                    </div>
                    <div className="var-config-field">
                      <label>Max</label>
                      <input
                        type="text"
                        placeholder="—"
                        value={f.max ?? ""}
                        onChange={(e) => updateField(i, { max: e.target.value })}
                      />
                    </div>
                  </>
                )}
                {f.type === "select" && (
                  <div className="var-config-field" style={{ flexBasis: "100%" }}>
                    <label>Options (comma-separated)</label>
                    <input
                      type="text"
                      placeholder="e.g. laminar, turbulent"
                      value={(f.options ?? []).join(", ")}
                      onChange={(e) =>
                        updateField(i, {
                          options: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                  </div>
                )}
              </div>
              <button
                type="button"
                className="edit-param-remove"
                onClick={() => removeField(i)}
                title="Remove parameter"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <button type="button" className="secondary sm" onClick={addField} style={{ marginTop: 12 }}>
        + Add Parameter
      </button>
    </>
  );
}
