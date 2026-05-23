"use client";

import Link from "next/link";
import { downloadUrl, type MassRun, type MassRunRun } from "@/lib/api";

function runStatusLabel(run: MassRunRun): string {
  if (run.status === "completed" && run.returncode === 0) return "Completed";
  if (run.status === "failed" || (run.status === "completed" && run.returncode != null && run.returncode !== 0)) {
    return "Failed";
  }
  if (run.status === "running") return "Running";
  return "Pending";
}

function runStatusClass(run: MassRunRun): string {
  if (run.status === "completed" && run.returncode === 0) return "ok";
  if (run.status === "failed" || (run.status === "completed" && run.returncode != null && run.returncode !== 0)) {
    return "fail";
  }
  if (run.status === "running") return "running";
  return "";
}

function isRunFinished(run: MassRunRun): boolean {
  return run.status === "completed" || run.status === "failed";
}

type Props = {
  massRun: MassRun;
  live?: boolean;
};

export function MassRunResultsTable({ massRun, live = false }: Props) {
  const runningCount = massRun.runs.filter((r) => r.status === "running").length;
  const pendingCount = massRun.runs.filter((r) => !isRunFinished(r) && r.status !== "running").length;
  const finishedCount = massRun.runs.filter(isRunFinished).length;

  return (
    <section className="panel" style={{ marginTop: 16 }}>
      <div className="panel-header">
        <div className="section-title" style={{ margin: 0 }}>Runs</div>
        {live && (
          <span className="run-live-indicator">
            <span className="run-live-dot" />
            Live
          </span>
        )}
      </div>

      {live && (
        <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 12px" }}>
          {runningCount > 0 && <span>{runningCount} running</span>}
          {runningCount > 0 && pendingCount > 0 && <span> · </span>}
          {pendingCount > 0 && <span>{pendingCount} queued</span>}
          {(runningCount > 0 || pendingCount > 0) && finishedCount > 0 && <span> · </span>}
          {finishedCount > 0 && <span>{finishedCount} finished</span>}
        </p>
      )}

      <div className="mass-run-table-wrap">
        <table className="mass-run-table mass-run-results-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Status</th>
              <th>Parameters</th>
              <th>Job</th>
              <th>Results</th>
            </tr>
          </thead>
          <tbody>
            {massRun.runs.map((run) => {
              const finished = isRunFinished(run);
              const rowClass = [
                run.status === "running" ? "mass-run-row-active" : "",
                finished && run.returncode === 0 ? "mass-run-row-done-ok" : "",
                finished && run.status === "failed" ? "mass-run-row-done-fail" : "",
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <tr key={run.job_id ?? `run-${run.index}`} className={rowClass || undefined}>
                  <td>{run.index + 1}</td>
                  <td>
                    <span className={`badge ${runStatusClass(run)}`}>{runStatusLabel(run)}</span>
                    {run.error_message && (
                      <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4, maxWidth: 220 }}>
                        {run.error_message}
                      </div>
                    )}
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {run.inputs.map((i) => (
                      <span key={i.label} style={{ marginRight: 12 }}>
                        <strong>{i.label}:</strong> {i.value}
                      </span>
                    ))}
                  </td>
                  <td>
                    {run.job_id ? (
                      <code style={{ fontSize: 11, color: "var(--muted)" }} title={run.job_id}>
                        {run.job_id.slice(0, 8)}…
                      </code>
                    ) : (
                      <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td>
                    {finished && run.job_id ? (
                      <div className="row gap-sm" style={{ flexWrap: "wrap" }}>
                        {run.status === "completed" && run.returncode === 0 && (
                          <Link href={`/jobs/${run.job_id}`} className="btn secondary sm">
                            View
                          </Link>
                        )}
                        <a href={downloadUrl(run.job_id)} download className="btn secondary sm">
                          Download
                        </a>
                      </div>
                    ) : run.status === "running" ? (
                      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>In progress…</span>
                    ) : (
                      <span style={{ fontSize: 12, color: "var(--muted)" }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
