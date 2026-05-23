"use client";

import type { ReactNode } from "react";
import type { ZipAnalysis } from "@/lib/api";

export type SimulationWizardCaseFileStepProps = {
  panelTitle?: string;
  zipInputId: string;
  zipLabel: string;
  zipRequired: boolean;
  hint: string;
  onZipSelected: (file: File) => void;
  selectedFileName?: string | null;
  onClearSelected?: () => void;
  analyzing: boolean;
  analysis: ZipAnalysis | null;
  expandedDirs: Set<string>;
  onToggleDir: (dir: string) => void;
  commands: string;
  onCommandsChange: (v: string) => void;
  /**
   * When true, show the commands textarea even without a fresh analysis (edit flow:
   * keep existing commands until / unless a new ZIP is analyzed).
   */
  showCommandsWithoutAnalysis?: boolean;
  commandsTextareaRows?: number;
  commandsHint?: string;
  /** When false, hide the run-commands textarea (e.g. result-case upload step). */
  showCommands?: boolean;
  /** Wizard Back / Next row, rendered inside the panel */
  footer?: ReactNode;
};

export function SimulationWizardCaseFileStep({
  panelTitle = "Case File",
  zipInputId,
  zipLabel,
  zipRequired,
  hint,
  onZipSelected,
  selectedFileName,
  onClearSelected,
  analyzing,
  analysis,
  expandedDirs,
  onToggleDir,
  commands,
  onCommandsChange,
  showCommandsWithoutAnalysis = false,
  commandsTextareaRows = 2,
  commandsHint,
  showCommands = true,
  footer,
}: SimulationWizardCaseFileStepProps) {
  const showCommandsBlock =
    showCommands && (Boolean(analysis) || showCommandsWithoutAnalysis);
  const defaultHint =
    commandsHint ??
    (analysis ? "Auto-detected from case. Edit if needed." : "Edit run commands for this template.");

  return (
    <section className="panel">
      <div className="panel-header">
        <div className="section-title" style={{ margin: 0 }}>{panelTitle}</div>
      </div>

      <div className="form-group">
        <label htmlFor={zipInputId}>
          {zipLabel}
          {zipRequired ? " *" : ""}
        </label>
        <input
          id={zipInputId}
          type="file"
          accept=".zip,application/zip"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onZipSelected(f);
          }}
        />
        <small className="hint">{hint}</small>
      </div>

      {selectedFileName && onClearSelected && (
        <p style={{ fontSize: 12, color: "var(--muted)", margin: "8px 0 0" }}>
          Selected: <code>{selectedFileName}</code>{" "}
          <button type="button" className="secondary sm" onClick={onClearSelected}>
            Clear
          </button>
        </p>
      )}

      {analyzing && (
        <div className="analyze-status">
          <div className="analyze-spinner" />
          <span>Analyzing case structure…</span>
        </div>
      )}

      {analysis && (
        <>
          <div className="analyze-insights">
            <div className="analyze-insight">
              <span className="analyze-insight-label">Solver</span>
              <code>{analysis.solver || "—"}</code>
            </div>
            <div className="analyze-insight">
              <span className="analyze-insight-label">Files</span>
              <code>{analysis.file_count}</code>
            </div>
            <div className="analyze-insight">
              <span className="analyze-insight-label">Has Allrun</span>
              <code>{analysis.has_allrun ? "Yes" : "No"}</code>
            </div>
            <div className="analyze-insight">
              <span className="analyze-insight-label">BlockMesh</span>
              <code>{analysis.has_blockmesh ? "Yes" : "No"}</code>
            </div>
          </div>

          <div className="form-group">
            <label>Case Structure</label>
            <div className="case-tree">
              {Object.entries(analysis.structure).map(([dir, files]) => (
                <div key={dir} className="case-tree-dir">
                  <button
                    type="button"
                    className="case-tree-toggle"
                    onClick={() => onToggleDir(dir)}
                  >
                    <span className="case-tree-arrow">
                      {expandedDirs.has(dir) ? "▾" : "▸"}
                    </span>
                    <span className="case-tree-dirname">{dir}/</span>
                    <span className="case-tree-count">{files.length}</span>
                  </button>
                  {expandedDirs.has(dir) && (
                    <div className="case-tree-files">
                      {files.map((f) => (
                        <div key={f} className="case-tree-file">
                          {f}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {showCommandsBlock && (
        <div className="form-group">
          <label htmlFor="wiz-case-commands">Run Commands</label>
          <textarea
            id="wiz-case-commands"
            value={commands}
            onChange={(e) => onCommandsChange(e.target.value)}
            spellCheck={false}
            rows={commandsTextareaRows}
            style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
          />
          <small className="hint">{defaultHint}</small>
        </div>
      )}
      {footer}
    </section>
  );
}
