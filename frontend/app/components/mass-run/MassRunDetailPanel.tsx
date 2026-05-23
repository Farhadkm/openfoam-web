"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MassRunResultsTable } from "@/app/components/mass-run/MassRunResultsTable";
import {
  fetchMassRun,
  massRunDownloadUrl,
  massRunResultsCsvUrl,
  type MassRun,
} from "@/lib/api";

type Props = {
  massRunId: string;
  showNewRunLink?: boolean;
  listHref?: string;
};

function isTerminalStatus(status: string): boolean {
  return status === "completed" || status === "completed_with_failures";
}

export function MassRunDetailPanel({ massRunId, showNewRunLink = false, listHref = "/history?tab=mass" }: Props) {
  const [massRun, setMassRun] = useState<MassRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    const data = await fetchMassRun(massRunId);
    setMassRun(data);
    return data;
  }, [massRunId]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    void refresh()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load mass run"))
      .finally(() => setLoading(false));
  }, [refresh]);

  const live = massRun != null && !isTerminalStatus(massRun.status);

  useEffect(() => {
    if (!live) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    const poll = () => void refresh().catch(() => {});
    poll();
    pollRef.current = setInterval(poll, 1000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [live, refresh]);

  const runStats = useMemo(() => {
    if (!massRun || massRun.total_runs === 0) {
      return { finished: 0, running: 0, pending: 0, pct: 0 };
    }
    const finished = massRun.runs.filter(
      (r) => r.status === "completed" || r.status === "failed",
    ).length;
    const running = massRun.runs.filter((r) => r.status === "running").length;
    const pending = massRun.total_runs - finished - running;
    const pct = Math.round((finished / massRun.total_runs) * 100);
    return { finished, running, pending, pct };
  }, [massRun]);

  if (loading) {
    return (
      <div className="panel">
        <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading mass run…</p>
      </div>
    );
  }

  if (error || !massRun) {
    return (
      <div className="panel" style={{ borderColor: "var(--danger)" }}>
        <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>
          {error ?? "Mass run not found"}
        </p>
      </div>
    );
  }

  const done = isTerminalStatus(massRun.status);
  const phaseLabel = live ? "Running" : massRun.failed_runs ? "Finished with failures" : "Completed";

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <div className="section-title" style={{ margin: 0 }}>
            {massRun.simulation_title}
          </div>
          <span className={`badge ${done ? (massRun.failed_runs ? "fail" : "ok") : "running"}`}>
            {phaseLabel}
          </span>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 8px" }}>
          Mass run ID:{" "}
          <code style={{ fontSize: 11 }} title={massRun.id}>
            {massRun.id}
          </code>
        </p>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 12px" }}>
          {massRun.completed_runs} succeeded · {massRun.failed_runs} failed · {massRun.total_runs}{" "}
          total · batch size {massRun.batch_size}
        </p>
        {live && (
          <>
            <div className="run-progress-bar mass-run-progress-bar" style={{ marginBottom: 8 }}>
              <div
                className="run-progress-bar-fill mass-run-progress-bar-fill"
                style={{ width: `${runStats.pct}%` }}
              />
            </div>
            <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
              {runStats.finished} of {massRun.total_runs} finished
              {runStats.running > 0 ? ` · ${runStats.running} running` : ""}
              {runStats.pending > 0 ? ` · ${runStats.pending} queued` : ""}
            </p>
          </>
        )}
      </section>

      <MassRunResultsTable massRun={massRun} live={live} />

      {(done || runStats.finished > 0) && (
        <div className="row gap-sm" style={{ marginTop: 16 }}>
          <a href={massRunResultsCsvUrl(massRunId)} download className="btn secondary">
            Download Results CSV
          </a>
          <a href={massRunDownloadUrl(massRunId)} download className="btn">
            {done ? "Download All Results (ZIP)" : "Download Finished Results (ZIP)"}
          </a>
          {showNewRunLink && (
            <Link href="/mass-run" className="btn secondary">
              New Mass Run
            </Link>
          )}
          <Link href={listHref} className="btn secondary">
            All Mass Runs
          </Link>
        </div>
      )}
    </>
  );
}
