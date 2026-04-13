"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  downloadUrl,
  fetchSimulation,
  jobWsUrl,
  runSimulation,
  simulationThumbnailUrl,
  type Simulation,
  type SimulationInputField,
} from "@/lib/api";
import { ChatBot } from "@/app/components/ChatBot";
import type { SimActionName } from "@/lib/aiChat";

type Phase = "configure" | "running" | "done";

export default function RunSimulationPage() {
  const params = useParams();
  const simId = typeof params?.id === "string" ? params.id : Array.isArray(params?.id) ? params.id[0] : "";

  const [sim, setSim] = useState<Simulation | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  /* input values keyed by field.key */
  const [inputs, setInputs] = useState<Record<string, string>>({});

  /* run state */
  const [phase, setPhase] = useState<Phase>("configure");
  const [jobId, setJobId] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  /* progress state */
  const [log, setLog] = useState("");
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [solverPhase, setSolverPhase] = useState<string | null>(null);
  const [solverTime, setSolverTime] = useState<string | null>(null);
  const [returncode, setReturncode] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const logRef = useRef<HTMLPreElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  /* load simulation details */
  useEffect(() => {
    if (!simId) return;
    fetchSimulation(simId)
      .then((data) => {
        setSim(data);
        const defaults: Record<string, string> = {};
        for (const f of data.input_fields) {
          defaults[f.key] = f.default;
        }
        setInputs(defaults);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load simulation"));
  }, [simId]);

  const setInput = (key: string, value: string) => {
    setInputs((prev) => ({ ...prev, [key]: value }));
  };

  const handleAIInputs = useCallback(
    (patch: Record<string, string>) => {
      setInputs((prev) => ({ ...prev, ...patch }));
    },
    [],
  );

  /* ref so the AI callback can always call the latest handleRun without stale closures */
  const handleRunRef = useRef<() => void>(() => {});

  const handleSimAction = useCallback(
    (action: SimActionName) => {
      if (action === "start_simulation") {
        handleRunRef.current();
      } else if (action === "reset_inputs") {
        if (!sim) return;
        const defaults: Record<string, string> = {};
        for (const f of sim.input_fields) {
          defaults[f.key] = f.default;
        }
        setInputs(defaults);
      }
    },
    [sim],
  );

  /* start the simulation */
  const handleRun = async () => {
    if (!sim) return;
    setSubmitting(true);
    setRunError(null);
    try {
      const result = await runSimulation(sim.id, inputs);
      setJobId(result.id);
      setPhase("running");
      setJobStatus("pending");
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Failed to start simulation");
    } finally {
      setSubmitting(false);
    }
  };

  handleRunRef.current = () => { void handleRun(); };

  /* WebSocket for progress tracking */
  useEffect(() => {
    if (!jobId || phase !== "running") return;

    const url = jobWsUrl(jobId);
    let retries = 0;
    const maxRetries = 10;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "log" && msg.chunk) {
            setLog((prev) => prev + msg.chunk);
            requestAnimationFrame(() => {
              if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            });
          }
          if (msg.type === "progress") {
            if (msg.phase) setSolverPhase(msg.phase);
            if (msg.time) setSolverTime(msg.time);
            if (msg.status) setJobStatus(msg.status);
          }
          if (msg.type === "hello" && msg.status) {
            setJobStatus(msg.status);
          }
          if (msg.type === "done") {
            setJobStatus(msg.status);
            setReturncode(msg.returncode ?? null);
            setErrorMsg(msg.error ?? null);
            setPhase("done");
          }
        } catch { /* ignore parse errors */ }
      };

      ws.onopen = () => { retries = 0; };

      ws.onclose = () => {
        if (phase === "running" && retries < maxRetries) {
          retries++;
          const delay = Math.min(1000 * 2 ** retries, 30000);
          timer = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      clearTimeout(timer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [jobId, phase]);

  /* auto-scroll log */
  const scrollToBottom = useCallback(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, []);

  useEffect(scrollToBottom, [log, scrollToBottom]);

  const statusLabel = useMemo(() => {
    if (jobStatus === "completed" && returncode === 0) return "Completed";
    if (jobStatus === "failed") return "Failed";
    if (jobStatus === "running") return "Running";
    if (jobStatus === "pending") return "Starting…";
    return jobStatus ?? "—";
  }, [jobStatus, returncode]);

  const statusClass = useMemo(() => {
    if (jobStatus === "completed" && returncode === 0) return "ok";
    if (jobStatus === "failed") return "fail";
    return "running";
  }, [jobStatus, returncode]);

  if (loadError) {
    return (
      <div className="panel" style={{ borderColor: "var(--danger)" }}>
        <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{loadError}</p>
        <Link href="/" className="btn secondary sm" style={{ marginTop: 12 }}>Back to Simulations</Link>
      </div>
    );
  }

  if (!sim) {
    return (
      <div className="panel">
        <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading simulation…</p>
      </div>
    );
  }

  const renderField = (field: SimulationInputField) => {
    if (field.type === "select" && field.options) {
      return (
        <select
          value={inputs[field.key] ?? field.default}
          onChange={(e) => setInput(field.key, e.target.value)}
          disabled={phase !== "configure"}
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    }
    return (
      <input
        type={field.type === "number" ? "number" : "text"}
        value={inputs[field.key] ?? field.default}
        onChange={(e) => setInput(field.key, e.target.value)}
        min={field.min}
        max={field.max}
        disabled={phase !== "configure"}
      />
    );
  };

  return (
    <>
      {/* ── Simulation header ── */}
      <div className="run-header">
        <div className="run-header-thumb">
          {sim.thumbnail_url ? (
            <img src={simulationThumbnailUrl(sim.id)} alt={sim.title} />
          ) : (
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
          )}
        </div>
        <div>
          <h2 className="run-header-title">{sim.title}</h2>
          <p className="run-header-desc">{sim.description}</p>
        </div>
      </div>

      {/* ── Phase: Configure ── */}
      {phase === "configure" && (
        <section className="panel">
          <div className="panel-header">
            <div className="section-title" style={{ margin: 0 }}>
              Configure Parameters
            </div>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {sim.input_fields.length} adjustable
            </span>
          </div>

          {sim.input_fields.length > 0 ? (
            <div className="run-params-grid">
              {sim.input_fields.map((field) => (
                <div key={field.key} className="run-param">
                  <label className="run-param-label">{field.label}</label>
                  {renderField(field)}
                  {(field.min || field.max) && (
                    <small className="hint">
                      {field.min && field.max
                        ? `Range: ${field.min} – ${field.max}`
                        : field.min
                          ? `Min: ${field.min}`
                          : `Max: ${field.max}`}
                    </small>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
              This simulation has no adjustable parameters. It will run with default settings.
            </p>
          )}

          {runError && (
            <p style={{ color: "var(--danger)", fontSize: 13, margin: "12px 0 0" }}>{runError}</p>
          )}

          <div className="row gap-sm" style={{ marginTop: 20 }}>
            <button type="button" disabled={submitting} onClick={() => void handleRun()}>
              {submitting ? "Starting…" : "Run Simulation"}
            </button>
            <Link href="/" className="btn secondary">Back</Link>
          </div>
        </section>
      )}

      {/* ── Phase: Running / Done ── */}
      {(phase === "running" || phase === "done") && (
        <>
          {/* Status bar */}
          <div className="run-status-bar">
            <div className="run-status-left">
              <span className={`badge ${statusClass}`}>{statusLabel}</span>
              {solverPhase && (
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  Solver: <code>{solverPhase}</code>
                </span>
              )}
              {solverTime && (
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  Time: <code>{solverTime}</code>
                </span>
              )}
            </div>
            {jobId && (
              <code style={{ fontSize: 11, color: "var(--muted)" }}>
                Job {jobId.slice(0, 8)}…
              </code>
            )}
          </div>

          {/* Progress bar for running state */}
          {phase === "running" && (
            <div className="run-progress-bar">
              <div className="run-progress-bar-fill" />
            </div>
          )}

          {/* Log output */}
          <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <div className="panel-header" style={{ padding: "10px 16px" }}>
              <div className="section-title" style={{ margin: 0, fontSize: 13 }}>Simulation Log</div>
              {phase === "running" && (
                <span className="run-live-indicator">
                  <span className="run-live-dot" />
                  Live
                </span>
              )}
            </div>
            <pre ref={logRef} className="run-log">
              {log || (phase === "running" ? "Waiting for output…" : "No log output.")}
            </pre>
          </section>

          {/* Error message */}
          {errorMsg && (
            <div className="panel" style={{ borderColor: "var(--danger)", marginTop: 12 }}>
              <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>
                <strong>Error:</strong> {errorMsg}
              </p>
            </div>
          )}

          {/* Done: results actions */}
          {phase === "done" && jobId && (
            <div className="run-results">
              <div className="section-title">Results</div>
              <div className="row gap-sm" style={{ flexWrap: "wrap" }}>
                {jobStatus === "completed" && returncode === 0 && (
                  <Link href={`/jobs/${jobId}`} className="btn">
                    View Visualization
                  </Link>
                )}
                <a href={downloadUrl(jobId)} download className="btn secondary">
                  Download Results
                </a>
                <Link href={`/simulations/${sim.id}/run`} className="btn secondary"
                  onClick={(e) => {
                    e.preventDefault();
                    setPhase("configure");
                    setJobId(null);
                    setLog("");
                    setJobStatus(null);
                    setSolverPhase(null);
                    setSolverTime(null);
                    setReturncode(null);
                    setErrorMsg(null);
                  }}
                >
                  Run Again
                </Link>
                <Link href="/" className="btn secondary">
                  Back to Simulations
                </Link>
              </div>
            </div>
          )}
        </>
      )}

      {sim && (
        <ChatBot
          pageContext="run"
          inputFields={sim.input_fields}
          onUpdateInputs={handleAIInputs}
          onSimAction={handleSimAction}
        />
      )}
    </>
  );
}
