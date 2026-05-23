/** Messages iframe (Trame) → parent (React). */
export type TrameStateMessage = {
  type: "forge-trame-state";
  payload: TrameViewerSnapshot;
};

/** Snapshot pushed from the Trame Python viewer (see backend/services/trame-viewer/app.py). */
export type TrameViewerSnapshot = {
  jobId: string;
  region: string;
  time: string;
  file: string;
  scalar: string;
  playing: boolean;
  show_streamlines: boolean;
  play_interval_sec: number;
  /** Simulation-time advance per play tick (same units as VTK time labels), discrete positive values only. */
  play_stride: number;
  status: string;
  times: string[];
  regions: string[];
  files: string[];
  scalars: string[];
};

/** Parent (React) → iframe (Trame bridge script). */
export type TrameParentMessage =
  | { type: "forge-trame-set-job"; jobId: string; autoLoad?: boolean }
  | { type: "forge-trame-patch-state"; patch: Record<string, unknown> }
  | { type: "forge-trame-cmd"; cmd: "prev" | "next" | "load" | "toggle_play" | "refresh" };

export function postToTrameViewer(win: Window | null | undefined, msg: TrameParentMessage, origin: string) {
  if (!win) return;
  try {
    win.postMessage(msg, origin);
  } catch {
    // ignore
  }
}
