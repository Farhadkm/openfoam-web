"use client";

import { useCallback, useState } from "react";
import {
  fetchSimulation,
  requestJobTroubleshoot,
  type Simulation,
  type TroubleshootRequest,
} from "@/lib/api";
import { extractFatalLogHints } from "@/lib/logUtils";

export type LogToolbarJobMeta = {
  status: string;
  returncode: number | null;
  error_message: string | null;
  commands?: string;
  simulation_id?: string;
};

type Props = {
  logText: string;
  jobId?: string | null;
  jobMeta?: LogToolbarJobMeta | null;
  simulation?: Simulation | null;
  inputsApplied?: Record<string, string> | null;
  /** When set, lazy-loads simulation template on AI debug if not passed. */
  simulationId?: string | null;
};

export function LogToolbar({
  logText,
  jobId,
  jobMeta,
  simulation,
  inputsApplied,
  simulationId,
}: Props) {
  const [copyLabel, setCopyLabel] = useState("Copy log");
  const [panelOpen, setPanelOpen] = useState(false);
  const [guide, setGuide] = useState<string | null>(null);
  const [guideCopyLabel, setGuideCopyLabel] = useState("Copy guide");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCopyLog = useCallback(async () => {
    const text = logText || "(empty)";
    try {
      await navigator.clipboard.writeText(text);
      setCopyLabel("Copied");
      setTimeout(() => setCopyLabel("Copy log"), 2000);
    } catch {
      setCopyLabel("Failed");
      setTimeout(() => setCopyLabel("Copy log"), 2000);
    }
  }, [logText]);

  const handleCopyGuide = useCallback(async () => {
    if (!guide) return;
    try {
      await navigator.clipboard.writeText(guide);
      setGuideCopyLabel("Copied");
      setTimeout(() => setGuideCopyLabel("Copy guide"), 2000);
    } catch {
      setGuideCopyLabel("Failed");
      setTimeout(() => setGuideCopyLabel("Copy guide"), 2000);
    }
  }, [guide]);

  const handleAiDebug = useCallback(async () => {
    if (!jobId) {
      setError("No job ID yet.");
      setPanelOpen(true);
      return;
    }
    setPanelOpen(true);
    setLoading(true);
    setError(null);
    setGuide(null);
    try {
      let sim = simulation ?? null;
      const simId = simulationId ?? jobMeta?.simulation_id;
      if (!sim && simId) {
        sim = await fetchSimulation(simId);
      }
      const body: TroubleshootRequest = {
        job_id: jobId,
        log: logText,
        job: {
          status: jobMeta?.status ?? "",
          returncode: jobMeta?.returncode ?? null,
          error_message: jobMeta?.error_message ?? null,
          commands: jobMeta?.commands ?? "",
        },
        simulation: sim
          ? {
              title: sim.title,
              commands: sim.commands,
              input_fields: sim.input_fields,
              result_fields: sim.result_fields,
            }
          : null,
        inputs_applied: inputsApplied ?? null,
        fatal_hints: extractFatalLogHints(logText),
      };
      const res = await requestJobTroubleshoot(body);
      setGuide(res.guide);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Troubleshooting request failed");
    } finally {
      setLoading(false);
    }
  }, [jobId, logText, jobMeta, simulation, simulationId, inputsApplied]);

  return (
    <div className="log-toolbar-wrap">
      <div className="log-toolbar row gap-sm">
        <button
          type="button"
          className="btn secondary btn-sm"
          onClick={() => void handleCopyLog()}
          aria-label="Copy full simulation log"
        >
          {copyLabel}
        </button>
        <button
          type="button"
          className="btn secondary btn-sm"
          onClick={() => void handleAiDebug()}
          disabled={loading}
          aria-label="AI troubleshoot simulation log"
          title="Analyze log with AI troubleshooting"
        >
          {loading ? "Analyzing…" : "AI debug"}
        </button>
        {panelOpen && guide && (
          <button
            type="button"
            className="btn secondary btn-sm"
            onClick={() => setPanelOpen(false)}
            aria-label="Close troubleshooting guide"
          >
            Close
          </button>
        )}
      </div>
      {panelOpen && (
        <div className="log-troubleshoot-panel panel" role="region" aria-label="AI troubleshooting guide">
          <div className="panel-header" style={{ padding: "8px 12px" }}>
            <div className="section-title" style={{ margin: 0, fontSize: 13 }}>
              Troubleshooting guide
            </div>
            {guide && (
              <button
                type="button"
                className="btn secondary btn-sm"
                onClick={() => void handleCopyGuide()}
              >
                {guideCopyLabel}
              </button>
            )}
          </div>
          <div className="log-troubleshoot-body">
            {loading && (
              <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>Analyzing log…</p>
            )}
            {error && (
              <p style={{ margin: 0, fontSize: 13, color: "var(--danger)" }}>{error}</p>
            )}
            {guide && (
              <pre className="log-troubleshoot-guide">{guide}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
