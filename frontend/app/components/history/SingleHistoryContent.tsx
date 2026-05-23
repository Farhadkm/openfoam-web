"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { downloadUrl, fetchJobs } from "@/lib/api";

type JobRow = {
  id: string;
  status: string;
  commands: string;
  returncode: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  run_instruction_name?: string;
};

export function SingleHistoryContent() {
  const router = useRouter();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data.jobs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const badgeCls = (status: string, rc: number | null) => {
    if (status === "completed" && rc === 0) return "ok";
    if (status === "failed") return "fail";
    if (status === "running" || status === "pending") return "running";
    return "";
  };

  const fmtDate = (iso: string) => {
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
  };

  return (
    <>
      <div className="page-desc">
        All single simulation runs with their status, timestamps, and results.
      </div>

      <section className="panel">
        <div className="panel-header">
          <div className="section-title" style={{ margin: 0 }}>
            Run History ({jobs.length})
          </div>
          <button type="button" className="secondary sm" onClick={() => void refresh()}>
            Refresh
          </button>
        </div>

        {loading ? (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading…</p>
        ) : error ? (
          <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{error}</p>
        ) : jobs.length === 0 ? (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>
            No runs yet. Go to Simulations to start one.
          </p>
        ) : (
          <div className="history-table-wrap">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Simulation</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Updated</th>
                  <th>Exit</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr
                    key={j.id}
                    className="history-table-row"
                    onClick={() => router.push(`/jobs/${j.id}`)}
                  >
                    <td>
                      <code className="job-id">{j.id.slice(0, 8)}…</code>
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                        {j.run_instruction_name || "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${badgeCls(j.status, j.returncode)}`}>{j.status}</span>
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                        {fmtDate(j.created_at)}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                        {fmtDate(j.updated_at)}
                      </span>
                    </td>
                    <td>
                      {j.returncode != null ? (
                        <code style={{ fontSize: 12 }}>{j.returncode}</code>
                      ) : (
                        <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>
                      )}
                    </td>
                    <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                      <div className="row gap-sm" style={{ justifyContent: "flex-end" }}>
                        <Link
                          className="btn secondary sm"
                          href={`/jobs/${j.id}`}
                          style={{ padding: "4px 8px", fontSize: 11 }}
                        >
                          Open
                        </Link>
                        <a
                          className="btn sm"
                          href={downloadUrl(j.id)}
                          download
                          style={{ padding: "4px 8px", fontSize: 11 }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          Download
                        </a>
                      </div>
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
