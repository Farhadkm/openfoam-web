"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MassRunPreviewEditor } from "@/app/components/mass-run/MassRunPreviewEditor";
import { MassRunDetailPanel } from "@/app/components/mass-run/MassRunDetailPanel";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";
import {
  fetchSimulations,
  previewMassRun,
  startMassRun,
  type MassRunPreview,
  type MassRunPreviewRun,
  type Simulation,
} from "@/lib/api";

type Phase = "setup" | "running";

export default function MassRunPage() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [simId, setSimId] = useState("");
  const [batchSize, setBatchSize] = useState(2);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<MassRunPreview | null>(null);
  const [editableRuns, setEditableRuns] = useState<MassRunPreviewRun[]>([]);
  const [phase, setPhase] = useState<Phase>("setup");
  const [massRunId, setMassRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSimulations()
      .then((data) => {
        setSimulations(data.simulations);
        if (data.simulations.length > 0) {
          setSimId((prev) => prev || data.simulations[0].id);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load simulations"))
      .finally(() => setLoading(false));
  }, []);

  const selectedSim = useMemo(
    () => simulations.find((s) => s.id === simId) ?? null,
    [simulations, simId],
  );

  const handleCsvChange = (file: File | null) => {
    setCsvFile(file);
    setPreview(null);
    setEditableRuns([]);
    setError(null);
  };

  const handlePreview = async () => {
    if (!simId || !csvFile) return;
    setPreviewing(true);
    setError(null);
    try {
      const data = await previewMassRun(simId, csvFile);
      setPreview(data);
      setEditableRuns(data.runs);
    } catch (e) {
      setPreview(null);
      setEditableRuns([]);
      setError(e instanceof Error ? e.message : "Failed to parse CSV");
    } finally {
      setPreviewing(false);
    }
  };

  const handleStart = async () => {
    if (!simId || editableRuns.length === 0) return;
    setStarting(true);
    setError(null);
    try {
      const started = await startMassRun(simId, {
        batch_size: batchSize,
        runs: editableRuns,
      });
      setMassRunId(started.id);
      setPhase("running");
      setPreview(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start mass run");
      setPhase("setup");
    } finally {
      setStarting(false);
    }
  };

  const reset = useCallback(() => {
    setPhase("setup");
    setMassRunId(null);
    setPreview(null);
    setEditableRuns([]);
    setCsvFile(null);
    setError(null);
  }, []);

  if (loading) {
    return (
      <div className="panel">
        <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading…</p>
      </div>
    );
  }

  return (
    <>
      <div className="page-desc">
        Upload a CSV where each row defines one simulation run. Columns alternate input label and
        value (e.g. <code>End Time,100,Velocity,5</code>). Runs execute in parallel batches via
        Docker.{" "}
        <Link href="/history?tab=mass">View past mass runs</Link>.
      </div>

      {error && (
        <div className="panel" style={{ borderColor: "var(--danger)", marginBottom: 16 }}>
          <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{error}</p>
        </div>
      )}

      {phase === "setup" && (
        <>
          {simulations.length === 0 ? (
            <div className="panel">
              <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
                Create a simulation template first.
              </p>
              <Link href="/simulations/new" className="btn secondary sm" style={{ marginTop: 12 }}>
                New Simulation
              </Link>
            </div>
          ) : (
            <section className="panel">
              <div className="panel-header">
                <div className="section-title" style={{ margin: 0 }}>
                  Configuration
                </div>
              </div>

              <div className="run-params-grid" style={{ marginBottom: 16 }}>
                <div className="run-param">
                  <label className="run-param-label">Simulation template</label>
                  <ForgeSelect
                    value={simId}
                    onChange={(v) => {
                      setSimId(v);
                      setPreview(null);
                      setEditableRuns([]);
                    }}
                    options={simulations.map((s) => ({
                      value: s.id,
                      label: s.title,
                    }))}
                    aria-label="Simulation template"
                  />
                </div>
                <div className="run-param">
                  <label className="run-param-label">Batch size</label>
                  <input
                    type="number"
                    min={1}
                    max={64}
                    value={batchSize}
                    onChange={(e) =>
                      setBatchSize(Math.max(1, Math.min(64, Number(e.target.value) || 1)))
                    }
                  />
                  <small className="hint">Max concurrent Docker runs (1–64)</small>
                </div>
                <div className="run-param" style={{ gridColumn: "1 / -1" }}>
                  <label className="run-param-label">Parameter CSV</label>
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(e) => handleCsvChange(e.target.files?.[0] ?? null)}
                  />
                  <small className="hint">
                    UTF-8 CSV; each row = one run; pairs: label, value, label, value… Labels must
                    match template parameter labels.
                  </small>
                </div>
              </div>

              {selectedSim && (
                <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 16px" }}>
                  Template has {selectedSim.input_fields.length} adjustable parameter
                  {selectedSim.input_fields.length === 1 ? "" : "s"}
                  {(selectedSim.result_fields ?? []).length > 0
                    ? ` and ${(selectedSim.result_fields ?? []).length} result field${(selectedSim.result_fields ?? []).length === 1 ? "" : "s"} for CSV export`
                    : ""}
                  .
                </p>
              )}

              <div className="row gap-sm">
                <button
                  type="button"
                  className="secondary"
                  disabled={!csvFile || previewing}
                  onClick={() => void handlePreview()}
                >
                  {previewing ? "Parsing…" : "Preview CSV"}
                </button>
              </div>
            </section>
          )}

          {preview && selectedSim && (
            <MassRunPreviewEditor
              fieldLabels={preview.field_labels}
              inputFields={selectedSim.input_fields}
              runs={editableRuns}
              batchSize={batchSize}
              starting={starting}
              onRunsChange={setEditableRuns}
              onStart={() => void handleStart()}
            />
          )}
        </>
      )}

      {phase === "running" && massRunId && (
        <>
          <div className="panel" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              Mass run started. ID:{" "}
              <code style={{ fontSize: 11 }} title={massRunId}>
                {massRunId}
              </code>{" "}
              —{" "}
              <Link href={`/history?tab=mass&id=${encodeURIComponent(massRunId ?? "")}`}>open in history</Link> (safe to leave this
              page).
            </p>
            <button type="button" className="secondary sm" style={{ marginTop: 12 }} onClick={reset}>
              Start another mass run
            </button>
          </div>
          <MassRunDetailPanel massRunId={massRunId} showNewRunLink />
        </>
      )}
    </>
  );
}
