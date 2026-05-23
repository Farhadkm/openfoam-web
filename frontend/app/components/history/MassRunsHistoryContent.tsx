"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchMassRuns, type MassRunListItem } from "@/lib/api";

type Props = {
  /** Build the href for opening a mass run detail view. Defaults to /history?tab=mass&id= */
  getDetailHref?: (massRunId: string) => string;
};

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

export function MassRunsHistoryContent({ getDetailHref }: Props) {
  const detailHref = getDetailHref ?? ((id: string) => `/history?tab=mass&id=${encodeURIComponent(id)}`);

  const [runs, setRuns] = useState<MassRunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMassRuns();
      setRuns(data.mass_runs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load mass runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const hasActive = runs.some((r) => r.status === "running" || r.status === "pending");
    if (!hasActive) return;
    const id = setInterval(() => void refresh(), 3000);
    return () => clearInterval(id);
  }, [runs, refresh]);

  return (
    <>
      <div className="page-desc">
        Past batch simulation runs from CSV uploads. Open a run to see per-job status, download a
        results CSV (inputs + template result fields), or download case ZIPs.
      </div>

      <div className="row gap-sm" style={{ marginBottom: 16 }}>
        <Link href="/mass-run" className="btn">
          New Mass Run
        </Link>
        <button type="button" className="secondary" onClick={() => void refresh()}>
          Refresh
        </button>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div className="section-title" style={{ margin: 0 }}>
            Mass Simulation Runs ({runs.length})
          </div>
        </div>

        {loading ? (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading…</p>
        ) : error ? (
          <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{error}</p>
        ) : runs.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
            No mass runs yet.{" "}
            <Link href="/mass-run">Start one</Link> from a simulation template and CSV.
          </p>
        ) : (
          <div className="mass-run-table-wrap">
            <table className="mass-run-table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Template</th>
                  <th>Status</th>
                  <th>Runs</th>
                  <th>ID</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>{fmtDate(run.created_at)}</td>
                    <td>{run.simulation_title || run.simulation_id}</td>
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
                      <Link href={detailHref(run.id)} className="btn secondary sm">
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
