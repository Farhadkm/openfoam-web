"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeAlertDialog, ThemeConfirmDialog } from "@/app/components/ui/ThemeDialogs";
import {
  fetchSimulations,
  simulationThumbnailUrl,
  deleteSimulation,
  type Simulation,
} from "@/lib/api";

/* ────────────────────────────── 3-Dot Menu ────────────────────────────── */

function CardMenu({
  onEdit,
  onDelete,
}: {
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="sim-card-menu" ref={ref}>
      <button
        className="sim-card-menu-btn"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label="Simulation options"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="8" cy="3" r="1.5" />
          <circle cx="8" cy="8" r="1.5" />
          <circle cx="8" cy="13" r="1.5" />
        </svg>
      </button>
      {open && (
        <div className="sim-card-dropdown">
          <button
            className="sim-card-dropdown-item"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
              onEdit();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
            Edit
          </button>
          <div className="sim-card-dropdown-divider" />
          <button
            className="sim-card-dropdown-item danger"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
              onDelete();
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────── Main Page ────────────────────────────── */

export default function SimulationsPage() {
  const router = useRouter();
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Simulation | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchSimulations();
      setSimulations(data.simulations);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load simulations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const confirmDeleteSimulation = async () => {
    if (!pendingDelete) return;
    const sim = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteSimulation(sim.id);
      setSimulations((prev) => prev.filter((s) => s.id !== sim.id));
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <>
      <div className="page-desc-row">
        <div className="page-desc">
          Select a simulation to configure and run. Each template includes a pre-configured CFD
          case with adjustable parameters.
        </div>
        <Link href="/simulations/new" className="btn" style={{ whiteSpace: "nowrap", flexShrink: 0 }}>
          + New Simulation
        </Link>
      </div>

      {error && (
        <div className="panel" style={{ borderColor: "var(--danger)", marginBottom: 16 }}>
          <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{error}</p>
        </div>
      )}

      {loading ? (
        <div className="panel">
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading simulations…</p>
        </div>
      ) : simulations.length === 0 ? (
        <div className="panel">
          <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: 13 }}>
            No simulations available yet. Create one to get started.
          </p>
          <Link href="/simulations/new" className="btn secondary sm" style={{ marginTop: 12 }}>
            Create Simulation
          </Link>
        </div>
      ) : (
        <div className="sim-grid">
          {simulations.map((sim) => (
            <div key={sim.id} className="sim-card">
              <CardMenu
                onEdit={() => router.push(`/simulations/${sim.id}/edit`)}
                onDelete={() => setPendingDelete(sim)}
              />
              <Link
                href={`/simulations/${sim.id}/run`}
                className="sim-card-link-inner"
              >
                <div className="sim-card-image">
                  {sim.thumbnail_url ? (
                    <img
                      src={simulationThumbnailUrl(sim.id)}
                      alt={sim.title}
                      className="sim-card-thumb"
                    />
                  ) : (
                    <div className="sim-card-thumb-placeholder">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="12 2 2 7 12 12 22 7 12 2" />
                        <polyline points="2 17 12 22 22 17" />
                        <polyline points="2 12 12 17 22 12" />
                      </svg>
                    </div>
                  )}
                </div>
                <div className="sim-card-body">
                  <h3 className="sim-card-title">{sim.title}</h3>
                  <p className="sim-card-desc">{sim.description || "No description provided."}</p>
                  <div className="sim-card-meta">
                    <span className="sim-card-arrow">Configure &amp; Run →</span>
                  </div>
                </div>
              </Link>
            </div>
          ))}
        </div>
      )}

      <ThemeConfirmDialog
        open={pendingDelete != null}
        title="Delete simulation"
        message={
          pendingDelete
            ? `Delete “${pendingDelete.title}”? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDeleteSimulation()}
      />

      <ThemeAlertDialog
        open={deleteError != null}
        title="Could not delete"
        message={deleteError ?? ""}
        onClose={() => setDeleteError(null)}
      />
    </>
  );
}
