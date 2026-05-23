"use client";

import { useEffect, useState } from "react";
import { fetchJobResultFields, type JobResultFieldValue } from "@/lib/api";

type Props = {
  jobId: string;
  /** When false, do not fetch (e.g. job still running). */
  enabled: boolean;
};

export function JobResultFieldsPanel({ jobId, enabled }: Props) {
  const [fields, setFields] = useState<JobResultFieldValue[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !jobId) {
      setFields(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchJobResultFields(jobId)
      .then((data) => {
        if (!cancelled) setFields(data.fields);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load result fields");
          setFields([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, enabled]);

  if (!enabled) return null;
  if (loading) {
    return (
      <p style={{ fontSize: 13, color: "var(--muted)", margin: "12px 0 0" }}>
        Loading result fields…
      </p>
    );
  }
  if (error) {
    return (
      <p style={{ fontSize: 13, color: "var(--danger)", margin: "12px 0 0" }}>
        {error}
      </p>
    );
  }
  if (!fields || fields.length === 0) return null;

  return (
    <div className="result-fields-panel" style={{ marginTop: 16 }}>
      <div className="section-title" style={{ fontSize: 14, marginBottom: 8 }}>
        Result Fields
      </div>
      <div className="result-fields-grid">
        {fields.map((f) => (
          <div key={f.key} className="result-field-card panel" style={{ padding: "10px 14px" }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>{f.label}</div>
            <code style={{ fontSize: 13 }}>{f.value || "—"}</code>
            {f.error && (
              <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4 }}>{f.error}</div>
            )}
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 6, fontFamily: "var(--font-mono)" }}>
              {f.key}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
