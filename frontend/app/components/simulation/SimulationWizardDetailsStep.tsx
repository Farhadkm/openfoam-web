"use client";

import type { ReactNode } from "react";
import { ThumbnailWithAiPicker } from "@/app/components/simulation/ThumbnailWithAiPicker";

export const SIMULATION_ENGINES = [{ value: "openfoam", label: "OpenFOAM" }];

type Props = {
  title: string;
  description: string;
  thumbnail: File | null;
  remotePreviewUrl: string | null;
  onTitle: (v: string) => void;
  onDescription: (v: string) => void;
  onThumbnail: (f: File | null) => void;
  engine: string;
  onEngine: (v: string) => void;
  /** Thumbnail AI brief */
  aiContextTitle: string;
  aiContextDescription: string;
  thumbnailLabel?: string;
  /** e.g. wizard Next / Cancel row, rendered inside the panel */
  footer?: ReactNode;
};

export function SimulationWizardDetailsStep({
  title,
  description,
  thumbnail,
  remotePreviewUrl,
  onTitle,
  onDescription,
  onThumbnail,
  engine,
  onEngine,
  aiContextTitle,
  aiContextDescription,
  thumbnailLabel = "Thumbnail Image (optional)",
  footer,
}: Props) {
  return (
    <section className="panel" style={{ maxWidth: 600 }}>
      <div className="panel-header">
        <div className="section-title" style={{ margin: 0 }}>Simulation Details</div>
      </div>

      <div className="form-group">
        <label htmlFor="wiz-engine">Simulation Engine</label>
        <select id="wiz-engine" value={engine} onChange={(e) => onEngine(e.target.value)}>
          {SIMULATION_ENGINES.map((eng) => (
            <option key={eng.value} value={eng.value}>
              {eng.label}
            </option>
          ))}
        </select>
        <small className="hint">More engines will be supported in future releases.</small>
      </div>

      <div className="form-group">
        <label htmlFor="wiz-title">Title *</label>
        <input
          id="wiz-title"
          type="text"
          placeholder="e.g. CPU Cabinet Cooling"
          value={title}
          onChange={(e) => onTitle(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="wiz-desc">Description</label>
        <textarea
          id="wiz-desc"
          placeholder="Briefly describe what this simulation does…"
          value={description}
          onChange={(e) => onDescription(e.target.value)}
          rows={3}
        />
      </div>

      <ThumbnailWithAiPicker
        label={thumbnailLabel}
        remotePreviewUrl={remotePreviewUrl}
        value={thumbnail}
        onChange={onThumbnail}
        title={aiContextTitle}
        description={aiContextDescription}
      />
      {footer}
    </section>
  );
}
