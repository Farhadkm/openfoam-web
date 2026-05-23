"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";
import {
  fetchMassRuns,
  fetchPredictiveModel,
  fetchPssModels,
  fetchSimulations,
  savePredictiveModel,
  trainPssModel,
  type MassRunListItem,
  type PssTrainedModel,
  type Simulation,
} from "@/lib/api";

type DatasetRole = "train" | "test" | null;

function statusBadgeClass(status: string): string {
  if (status === "completed") return "ok";
  if (status === "completed_with_failures") return "fail";
  if (status === "running" || status === "pending") return "running";
  if (status === "failed") return "fail";
  return "";
}

function statusLabel(status: string): string {
  if (status === "completed") return "Completed";
  if (status === "completed_with_failures") return "Completed (failures)";
  if (status === "running") return "Running";
  if (status === "pending") return "Pending";
  if (status === "failed") return "Failed";
  return status;
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso);
    return (
      d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) +
      " " +
      d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    );
  } catch {
    return iso;
  }
}

function rolesFromConfig(
  training: string[],
  testing: string[],
): Record<string, DatasetRole> {
  const map: Record<string, DatasetRole> = {};
  for (const id of training) map[id] = "train";
  for (const id of testing) map[id] = "test";
  return map;
}

function configFromRoles(roles: Record<string, DatasetRole>) {
  const training_mass_run_ids: string[] = [];
  const testing_mass_run_ids: string[] = [];
  for (const [id, role] of Object.entries(roles)) {
    if (role === "train") training_mass_run_ids.push(id);
    if (role === "test") testing_mass_run_ids.push(id);
  }
  return { training_mass_run_ids, testing_mass_run_ids };
}

export default function SimulationPredictiveModelPage() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [simId, setSimId] = useState("");
  const [runs, setRuns] = useState<MassRunListItem[]>([]);
  const [roles, setRoles] = useState<Record<string, DatasetRole>>({});
  const [savedRoles, setSavedRoles] = useState<Record<string, DatasetRole>>({});
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [saving, setSaving] = useState(false);
  const [training, setTraining] = useState(false);
  const [trainedModels, setTrainedModels] = useState<PssTrainedModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [trainMessage, setTrainMessage] = useState<string | null>(null);

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

  const loadForSimulation = useCallback(async (id: string) => {
    if (!id) return;
    setLoadingRuns(true);
    setError(null);
    setSaveMessage(null);
    try {
      const [runsData, config, modelsData] = await Promise.all([
        fetchMassRuns(id),
        fetchPredictiveModel(id),
        fetchPssModels(id).catch(() => ({ simulation_id: id, models: [] as PssTrainedModel[] })),
      ]);
      setRuns(runsData.mass_runs);
      setTrainedModels(modelsData.models);
      const nextRoles = rolesFromConfig(
        config.training_mass_run_ids,
        config.testing_mass_run_ids,
      );
      setRoles(nextRoles);
      setSavedRoles(nextRoles);
      setLastSavedAt(config.updated_at);
    } catch (e) {
      setRuns([]);
      setTrainedModels([]);
      setRoles({});
      setSavedRoles({});
      setLastSavedAt(null);
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    if (!simId) return;
    void loadForSimulation(simId);
  }, [simId, loadForSimulation]);

  const selectedSim = useMemo(
    () => simulations.find((s) => s.id === simId) ?? null,
    [simulations, simId],
  );

  const dirty = useMemo(() => {
    const current = configFromRoles(roles);
    const saved = configFromRoles(savedRoles);
    const sort = (a: string[]) => [...a].sort().join(",");
    return (
      sort(current.training_mass_run_ids) !== sort(saved.training_mass_run_ids) ||
      sort(current.testing_mass_run_ids) !== sort(saved.testing_mass_run_ids)
    );
  }, [roles, savedRoles]);

  const counts = useMemo(() => {
    let train = 0;
    let test = 0;
    for (const role of Object.values(roles)) {
      if (role === "train") train += 1;
      if (role === "test") test += 1;
    }
    return { train, test, unassigned: runs.length - train - test };
  }, [roles, runs.length]);

  const setRole = (massRunId: string, role: DatasetRole) => {
    setRoles((prev) => {
      const next = { ...prev };
      if (role === null) {
        delete next[massRunId];
      } else {
        next[massRunId] = role;
      }
      return next;
    });
    setSaveMessage(null);
  };

  const handleTrain = async () => {
    if (!simId) return;
    setTraining(true);
    setError(null);
    setTrainMessage(null);
    try {
      const body = configFromRoles(roles);
      const model = await trainPssModel(simId, {
        training_mass_run_ids: body.training_mass_run_ids,
        testing_mass_run_ids: body.testing_mass_run_ids,
      });
      const modelsData = await fetchPssModels(simId);
      setTrainedModels(modelsData.models);
      const agg = model.metrics?.aggregate;
      setTrainMessage(
        `Trained model ${model.id.slice(0, 8)}… — test R² ${agg?.r2 != null ? agg.r2.toFixed(3) : "n/a"}, RMSE ${agg?.rmse != null ? agg.rmse.toFixed(4) : "n/a"}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Training failed");
    } finally {
      setTraining(false);
    }
  };

  const handleSave = async () => {
    if (!simId) return;
    setSaving(true);
    setError(null);
    setSaveMessage(null);
    try {
      const body = configFromRoles(roles);
      const saved = await savePredictiveModel(simId, body);
      const nextRoles = rolesFromConfig(
        saved.training_mass_run_ids,
        saved.testing_mass_run_ids,
      );
      setRoles(nextRoles);
      setSavedRoles(nextRoles);
      setLastSavedAt(saved.updated_at);
      setSaveMessage("Training and testing assignments saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const simOptions = simulations.map((s) => ({
    value: s.id,
    label: s.title || s.id,
  }));

  return (
    <>
      <div className="page-desc">
        Choose a simulation template, then assign its past mass simulation runs to a{" "}
        <strong>training</strong> or <strong>testing</strong> set for predictive modeling. Assignments
        are stored on the server and persist across refreshes.{" "}
        <Link href="/mass-run">Start a mass run</Link> or{" "}
        <Link href="/history?tab=mass">view history</Link> if you need more data.
      </div>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header">
          <div className="section-title" style={{ margin: 0 }}>
            Simulation template
          </div>
        </div>
        {loading ? (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading simulations…</p>
        ) : simulations.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
            No simulations yet. <Link href="/simulations/new">Create one</Link> first.
          </p>
        ) : (
          <div className="field" style={{ maxWidth: 420 }}>
            <label htmlFor="predictive-sim-select">Template</label>
            <ForgeSelect
              id="predictive-sim-select"
              value={simId}
              onChange={setSimId}
              options={simOptions}
              placeholder="Select simulation…"
            />
            {selectedSim?.description ? (
              <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}>
                {selectedSim.description}
              </p>
            ) : null}
          </div>
        )}
      </section>

      {simId && (
        <section className="panel">
          <div className="panel-header row gap-sm" style={{ flexWrap: "wrap", alignItems: "center" }}>
            <div className="section-title" style={{ margin: 0 }}>
              Mass runs for {selectedSim?.title || simId} ({runs.length})
            </div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="badge ok" style={{ fontSize: 11 }}>
                Training: {counts.train}
              </span>
              <span className="badge running" style={{ fontSize: 11 }}>
                Testing: {counts.test}
              </span>
              <span className="badge" style={{ fontSize: 11 }}>
                Unassigned: {counts.unassigned}
              </span>
            </div>
          </div>

          <div className="row gap-sm" style={{ marginBottom: 16, flexWrap: "wrap" }}>
            <button
              type="button"
              className="secondary"
              onClick={() => void loadForSimulation(simId)}
              disabled={loadingRuns}
            >
              Refresh
            </button>
            <button type="button" onClick={() => void handleSave()} disabled={saving || !dirty}>
              {saving ? "Saving…" : "Save assignments"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void handleTrain()}
              disabled={training || counts.train === 0}
              title={counts.train === 0 ? "Assign at least one training mass run" : undefined}
            >
              {training ? "Training XGBoost…" : "Train XGBoost"}
            </button>
            {lastSavedAt ? (
              <span style={{ fontSize: 12, color: "var(--muted)", alignSelf: "center" }}>
                Last saved {fmtDate(lastSavedAt)}
              </span>
            ) : null}
          </div>

          {saveMessage ? (
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--accent)" }}>{saveMessage}</p>
          ) : null}
          {trainMessage ? (
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--accent)" }}>{trainMessage}</p>
          ) : null}
          {error ? (
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--danger)" }}>{error}</p>
          ) : null}

          {loadingRuns ? (
            <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading mass runs…</p>
          ) : runs.length === 0 ? (
            <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
              No mass runs for this simulation yet.{" "}
              <Link href="/mass-run">Run a batch</Link> from CSV to build a dataset.
            </p>
          ) : (
            <div className="mass-run-table-wrap">
              <table className="mass-run-table">
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Status</th>
                    <th>Runs</th>
                    <th>ID</th>
                    <th>Dataset split</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const role = roles[run.id] ?? null;
                    return (
                      <tr key={run.id}>
                        <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>{fmtDate(run.created_at)}</td>
                        <td>
                          <span className={`badge ${statusBadgeClass(run.status)}`}>
                            {statusLabel(run.status)}
                          </span>
                        </td>
                        <td style={{ fontSize: 12 }}>
                          {run.completed_runs} ok · {run.failed_runs} failed · {run.total_runs} total
                        </td>
                        <td>
                          <code style={{ fontSize: 11, color: "var(--muted)" }} title={run.id}>
                            {run.id.slice(0, 8)}…
                          </code>
                        </td>
                        <td>
                          <div
                            className="row gap-sm"
                            style={{ flexWrap: "nowrap" }}
                            role="group"
                            aria-label={`Dataset assignment for mass run ${run.id}`}
                          >
                            <button
                              type="button"
                              className={`btn sm${role === "train" ? "" : " secondary"}`}
                              aria-pressed={role === "train"}
                              onClick={() => setRole(run.id, role === "train" ? null : "train")}
                            >
                              Training
                            </button>
                            <button
                              type="button"
                              className={`btn sm${role === "test" ? "" : " secondary"}`}
                              aria-pressed={role === "test"}
                              onClick={() => setRole(run.id, role === "test" ? null : "test")}
                            >
                              Testing
                            </button>
                            {role ? (
                              <button
                                type="button"
                                className="btn secondary sm"
                                onClick={() => setRole(run.id, null)}
                              >
                                Clear
                              </button>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <Link href={`/history?tab=mass&id=${encodeURIComponent(run.id)}`} className="btn secondary sm">
                            Open
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {trainedModels.length > 0 ? (
            <div style={{ marginTop: 24 }}>
              <div className="section-title" style={{ fontSize: 14, marginBottom: 8 }}>
                Trained models ({trainedModels.length})
              </div>
              <div className="mass-run-table-wrap">
                <table className="mass-run-table">
                  <thead>
                    <tr>
                      <th>Created</th>
                      <th>Technique</th>
                      <th>Train rows</th>
                      <th>Test R²</th>
                      <th>ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trainedModels.map((m) => (
                      <tr key={m.id}>
                        <td style={{ fontSize: 12 }}>{fmtDate(m.created_at)}</td>
                        <td>{m.technique}</td>
                        <td style={{ fontSize: 12 }}>{m.n_train_rows}</td>
                        <td style={{ fontSize: 12 }}>
                          {m.metrics?.aggregate?.r2 != null
                            ? m.metrics.aggregate.r2.toFixed(3)
                            : "—"}
                        </td>
                        <td>
                          <code style={{ fontSize: 11 }}>{m.id.slice(0, 8)}…</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </section>
      )}
    </>
  );
}
