"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import {
  downloadUrl,
  fetchCaseFileText,
  fetchJob,
  fetchJobLog,
  fetchJobOutputs,
  jobWsUrl,
  type Job,
} from "@/lib/api";
import { postToTrameViewer, type TrameViewerSnapshot } from "@/lib/trameBridge";
import Link from "next/link";
import {
  trameCanvasViewerSrc,
  trameFramePostMessageTarget,
  trameOriginAcceptsMessage,
  tramePublicOrigin,
} from "@/lib/trame";
import { JobResultFieldsPanel } from "@/app/components/simulation/JobResultFieldsPanel";
import { ViewerTimeRail } from "@/app/components/ViewerTimeRail";
import { ViewerPlaySpeedControl } from "@/app/components/ViewerPlaySpeedControl";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";
import {
  formatPlayTimeStepLabel,
  playTimeStepChoiceIndex,
  vtkPlayTimeStepChoices,
  vtkTimeMinGap,
} from "@/lib/vtkPlayTimeStep";
import { ChatBot } from "@/app/components/ChatBot";
import { LogToolbar } from "@/app/components/LogToolbar";
import {
  buildJobPipelineSteps,
  computeJobStepStatuses,
  type StepDisplayStatus,
} from "@/lib/jobPipelineSteps";

function pipelineStatusLabel(s: StepDisplayStatus): string {
  switch (s) {
    case "done":
      return "Done";
    case "active":
      return "In progress";
    case "pending":
      return "Waiting";
    case "failed":
      return "Failed";
    case "skipped":
      return "Skipped";
    default:
      return s;
  }
}

type LocalControls = {
  time: string;
  region: string;
  file: string;
  scalar: string;
  show_streamlines: boolean;
  /** Seconds between VTK frames while Play is on (Trame `play_interval_sec`). */
  play_interval_sec: number;
  /** Simulation-time step per play tick (same units as VTK times). */
  play_stride: number;
};

const SNAP_SETTLE_MS = 600;

/** Parse `startTime` / `endTime` from controlDict for simulation-time progress. */
function parseControlDictTimes(text: string): { start: number; end: number } | null {
  const endM = text.match(/^\s*endTime\s+([\d.eE+-]+)\s*;/m);
  if (!endM) return null;
  const end = parseFloat(endM[1]);
  const startM = text.match(/^\s*startTime\s+([\d.eE+-]+)\s*;/m);
  const start = startM ? parseFloat(startM[1]) : 0;
  if (!Number.isFinite(end) || !Number.isFinite(start) || end <= start) return null;
  return { start, end };
}

/** Rough pipeline order for log lines `Running <utility> on …` (many solvers missing from old list caused ~36% to stick). */
const PIPELINE_PHASES = [
  "blockMesh",
  "surfaceFeatureExtract",
  "snappyHexMesh",
  "topoSet",
  "createPatch",
  "decomposePar",
  "splitMeshRegions",
  "redistributeMeshPar",
  "reconstructParMesh",
  "mapFields",
  "setFields",
  "checkMesh",
  "potentialFoam",
  "icoFoam",
  "simpleFoam",
  "pimpleFoam",
  "PIMPLE",
  "interFoam",
  "chtMultiRegionSimpleFoam",
  "chtMultiRegionFoam",
  "scalarTransportFoam",
  "foamToVTK",
  "reconstructPar",
];

export default function JobVisualizePage() {
  const params = useParams();
  const pathname = usePathname();
  const jobId = useMemo(() => {
    const r = params?.jobId;
    const fromParams = typeof r === "string" ? r : Array.isArray(r) ? r[0] : undefined;
    if (fromParams) return fromParams;
    const m = pathname?.match(/^\/jobs\/([^/?#]+)/);
    return m?.[1];
  }, [params?.jobId, pathname]);
  const [log, setLog] = useState<string>("");
  const [live, setLive] = useState(false);
  const [progressOpen, setProgressOpen] = useState(true);
  const [phase, setPhase] = useState<string | null>(null);
  const [tcur, setTcur] = useState<string | null>(null);
  const [jobMeta, setJobMeta] = useState<Job | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [returncode, setReturncode] = useState<number | null>(null);
  const [controlTimeRange, setControlTimeRange] = useState<{ start: number; end: number } | null>(null);
  const [outputs, setOutputs] = useState<{
    times: string[];
    regions: string[];
    has_vtk: boolean;
    has_foam: boolean;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const viewerIframeRef = useRef<HTMLIFrameElement>(null);
  const [trameSnap, setTrameSnap] = useState<TrameViewerSnapshot | null>(null);

  const [local, setLocal] = useState<LocalControls | null>(null);
  const lastUserChange = useRef(0);

  useEffect(() => {
    if (!trameSnap) { setLocal(null); return; }
    const elapsed = Date.now() - lastUserChange.current;
    const blocked = elapsed < SNAP_SETTLE_MS;
    if (blocked) return;
    setLocal({
      time: trameSnap.time,
      region: trameSnap.region,
      file: trameSnap.file,
      scalar: trameSnap.scalar,
      show_streamlines: trameSnap.show_streamlines,
      play_interval_sec: Number(trameSnap.play_interval_sec) || 0,
      play_stride: Number(trameSnap.play_stride) || 0,
    });
  }, [trameSnap]);

  const download = useMemo(() => (jobId ? downloadUrl(jobId) : ""), [jobId]);
  const [canvasSrc, setCanvasSrc] = useState("");
  const iframeEpoch = useRef(0);
  const watchdogRetries = useRef(0);

  const trameWin = () => viewerIframeRef.current?.contentWindow ?? null;

  const sendPatch = useCallback((patch: Record<string, unknown>) => {
    const w = trameWin();
    if (!w) return;
    postToTrameViewer(w, { type: "forge-trame-patch-state", patch }, trameFramePostMessageTarget());
  }, []);

  const changeControl = useCallback(
    <K extends keyof LocalControls>(key: K, value: LocalControls[K], doLoad = true) => {
      lastUserChange.current = Date.now();
      setLocal((prev) => (prev ? { ...prev, [key]: value } : prev));
      sendPatch({ [key]: value, doLoad });
    },
    [sendPatch],
  );

  /** Time slider / rail: works even before `local` syncs from the iframe bridge. */
  const selectTime = useCallback(
    (t: string) => {
      lastUserChange.current = Date.now();
      setLocal((prev) => {
        if (prev) return { ...prev, time: t };
        const snap = trameSnap;
        if (!snap) return null;
        return {
          time: t,
          region: snap.region,
          file: snap.file,
          scalar: snap.scalar,
          show_streamlines: snap.show_streamlines,
          play_interval_sec: Number(snap.play_interval_sec) || 0,
          play_stride: Number(snap.play_stride) || 0,
        };
      });
      sendPatch({ time: t, doLoad: true });
    },
    [sendPatch, trameSnap],
  );

  const sendCmd = useCallback((cmd: "prev" | "next" | "load" | "toggle_play" | "refresh") => {
    const w = trameWin();
    if (!w) return;
    postToTrameViewer(w, { type: "forge-trame-cmd", cmd }, trameFramePostMessageTarget());
  }, []);

  const viewerStateForAI = useMemo(() => {
    if (!trameSnap) return null;
    return {
      time: trameSnap.time,
      times: trameSnap.times,
      region: trameSnap.region,
      regions: trameSnap.regions,
      file: trameSnap.file,
      files: trameSnap.files,
      scalar: trameSnap.scalar,
      scalars: trameSnap.scalars,
      playing: trameSnap.playing,
      show_streamlines: trameSnap.show_streamlines,
      play_interval_sec: trameSnap.play_interval_sec,
      play_stride: trameSnap.play_stride,
    };
  }, [trameSnap]);

  const playStrideChoices = useMemo(
    () => vtkPlayTimeStepChoices(trameSnap?.times ?? []),
    [trameSnap?.times],
  );
  const playStepMinGap = useMemo(() => vtkTimeMinGap(trameSnap?.times ?? []), [trameSnap?.times]);

  const handleViewerCmd = useCallback(
    (cmd: Record<string, unknown>) => {
      const action = cmd.action as string | undefined;
      if (!action) return;
      console.debug("[handleViewerCmd]", action, cmd);
      switch (action) {
        case "set_time":
          if (typeof cmd.value === "string") sendPatch({ time: cmd.value, doLoad: true });
          break;
        case "prev_time":
          sendCmd("prev");
          break;
        case "next_time":
          sendCmd("next");
          break;
        case "play":
          sendPatch({ playing: true });
          break;
        case "pause":
          sendPatch({ playing: false });
          break;
        case "set_scalar":
          if (typeof cmd.value === "string") sendPatch({ scalar: cmd.value, doLoad: true });
          break;
        case "set_file":
          if (typeof cmd.value === "string") sendPatch({ file: cmd.value, doLoad: true });
          break;
        case "set_region":
          if (typeof cmd.value === "string") sendPatch({ region: cmd.value, doLoad: true });
          break;
        case "toggle_streamlines":
          sendPatch({ show_streamlines: Boolean(cmd.value), doLoad: true });
          break;
        case "load":
          sendCmd("load");
          break;
        case "refresh":
          sendCmd("refresh");
          break;
      }
    },
    [sendPatch, sendCmd],
  );

  const jobFinishedOk = jobStatus === "completed" && returncode === 0;
  const jobTerminal = jobFinishedOk || jobStatus === "failed" || (jobStatus === "completed" && returncode !== 0 && returncode != null);
  const showViz = Boolean(jobFinishedOk && outputs?.has_vtk);

  // Watchdog: if the trame iframe hasn't sent a state message within
  // WATCHDOG_MS after the iframe loaded, force-reload it (up to MAX_RETRIES).
  const WATCHDOG_MS = 12_000;
  const MAX_RETRIES = 3;
  useEffect(() => {
    if (!canvasSrc || !showViz) { watchdogRetries.current = 0; return; }
    const tid = window.setTimeout(() => {
      if (trameSnap) return;
      if (watchdogRetries.current >= MAX_RETRIES) return;
      watchdogRetries.current += 1;
      iframeEpoch.current += 1;
      setCanvasSrc("");
      requestAnimationFrame(() =>
        setCanvasSrc(trameCanvasViewerSrc(jobId ?? "", window.location.origin)),
      );
    }, WATCHDOG_MS);
    return () => window.clearTimeout(tid);
  }, [canvasSrc, showViz, trameSnap, jobId]);

  useEffect(() => {
    if (jobTerminal) setProgressOpen(false);
  }, [jobTerminal]);

  const phaseStepPct = useMemo(() => {
    if (!phase) return 0;
    const idx = PIPELINE_PHASES.indexOf(phase);
    if (idx >= 0) return Math.round(((idx + 1) / PIPELINE_PHASES.length) * 100);
    if (/Foam$/i.test(phase)) return 78;
    return 12;
  }, [phase]);

  const canUseTimeProgress =
    (jobStatus === "running" || jobStatus === "pending") &&
    controlTimeRange != null &&
    tcur != null &&
    Number.isFinite(parseFloat(tcur));

  const progressFillPct = useMemo(() => {
    if (jobFinishedOk) return 100;
    if (jobStatus === "failed") return 100;
    if (canUseTimeProgress && controlTimeRange) {
      const t = parseFloat(tcur!);
      const { start, end } = controlTimeRange;
      const timePct = ((t - start) / (end - start)) * 100;
      const blended = Math.max(phaseStepPct, timePct);
      return Math.round(Math.min(99, Math.max(2, blended)));
    }
    return phaseStepPct;
  }, [jobFinishedOk, jobStatus, canUseTimeProgress, controlTimeRange, tcur, phaseStepPct]);

  const progressIndeterminate =
    (jobStatus === "running" || jobStatus === "pending") && !canUseTimeProgress;

  const pipelineSteps = useMemo(
    () => buildJobPipelineSteps(jobMeta?.commands ?? ""),
    [jobMeta?.commands],
  );

  const pipelineWithStatus = useMemo(
    () =>
      computeJobStepStatuses(pipelineSteps, {
        log,
        jobStatus,
        returncode,
      }),
    [pipelineSteps, log, jobStatus, returncode],
  );

  const progressHint = useMemo(() => {
    if (jobFinishedOk) return "Complete";
    if (jobStatus === "failed") return "Finished with errors";
    if (canUseTimeProgress && controlTimeRange) {
      return `${progressFillPct}% (simulation time vs endTime in controlDict; phase: ${phase ?? "—"})`;
    }
    if (progressIndeterminate) {
      return "Time-based estimate unavailable (open controlDict after the case exists). Showing activity…";
    }
    return `${progressFillPct}% (last log phase: ${phase ?? "—"})`;
  }, [
    jobFinishedOk,
    jobStatus,
    canUseTimeProgress,
    controlTimeRange,
    progressFillPct,
    progressIndeterminate,
    phase,
  ]);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    setErr(null);
    try {
      const [j, l, o] = await Promise.all([fetchJob(jobId), fetchJobLog(jobId), fetchJobOutputs(jobId)]);
      setJobMeta(j);
      setJobStatus(j.status);
      setReturncode(j.returncode);
      setLog(l.log ?? "");
      setOutputs({ times: o.times, regions: o.regions, has_vtk: o.has_vtk, has_foam: o.has_foam });

      try {
        const cd = await fetchCaseFileText(jobId, "system/controlDict");
        setControlTimeRange(parseControlDictTimes(cd));
      } catch {
        setControlTimeRange(null);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load job");
    }
  }, [jobId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setTrameSnap(null);
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !showViz) {
      setCanvasSrc("");
      return;
    }
    setCanvasSrc(trameCanvasViewerSrc(jobId, window.location.origin));
  }, [jobId, showViz]);

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const tramePub = tramePublicOrigin();
      const fromApp = e.origin === window.location.origin;
      const fromTrame = trameOriginAcceptsMessage(tramePub, e.origin);
      if (!fromApp && !fromTrame) return;
      if (e.data?.type === "forge-trame-state" && e.data.payload) {
        setTrameSnap(e.data.payload as TrameViewerSnapshot);
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      setLive(false);
      ws = new WebSocket(jobWsUrl(jobId));

      ws.onopen = () => {
        setLive(true);
        attempts = 0;
      };
      ws.onclose = () => {
        setLive(false);
        if (closed) return;
        attempts += 1;
        if (attempts > 10) return;
        const delay = Math.min(1000 * 2 ** (attempts - 1), 30000);
        timer = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        // will trigger onclose
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as any;
          if (msg.type === "hello" && typeof msg.status === "string") {
            setJobStatus(msg.status);
          }
          if (msg.type === "log" && typeof msg.chunk === "string") {
            setLog((prev) => (prev ? prev + msg.chunk : msg.chunk));
          }
          if (msg.type === "progress") {
            if (typeof msg.phase === "string" || msg.phase === null) setPhase(msg.phase ?? null);
            if (typeof msg.time === "string" || msg.time === null) setTcur(msg.time ?? null);
            if (typeof msg.status === "string") setJobStatus(msg.status);
          }
          if (msg.type === "done") {
            if (typeof msg.status === "string") setJobStatus(msg.status);
            if (typeof msg.returncode === "number") setReturncode(msg.returncode);
            void refresh();
          }
        } catch {
          // ignore
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      try {
        ws?.close();
      } catch {
        // ignore
      }
      ws = null;
    };
  }, [jobId, refresh]);

  useEffect(() => {
    if (!showViz) setTrameSnap(null);
  }, [showViz]);

  return (
    <>
      {/* ── Job summary (run configuration) ── */}
      <section className="panel">
        <div className="section-title">Job</div>
        {jobMeta ? (
          <div className="kvs">
            <div className="kvk">Job ID</div>
            <div><code>{jobMeta.id}</code></div>
            <div className="kvk">Template</div>
            <div>
              {jobMeta.simulation_id ? (
                <>
                  <Link href={`/simulations/${jobMeta.simulation_id}/edit`}>
                    {jobMeta.run_instruction_name || "Edit simulation"}
                  </Link>
                  <span style={{ display: "block", marginTop: 6, fontSize: 12, color: "var(--muted)" }}>
                    Commands below are the snapshot stored when this job started. If you changed the template
                    afterward, the simulation&apos;s current commands can differ.
                  </span>
                </>
              ) : (
                <span>{jobMeta.run_instruction_name || "—"}</span>
              )}
            </div>
            <div className="kvk">Status</div>
            <div>
              <span
                className={`badge ${
                  jobFinishedOk
                    ? "ok"
                    : jobStatus === "failed" || (jobStatus === "completed" && returncode !== 0 && returncode != null)
                      ? "fail"
                      : "running"
                }`}
              >
                {jobStatus ?? jobMeta.status}
              </span>
              {returncode != null && (
                <span style={{ marginLeft: 8, fontSize: 12, color: "var(--text-secondary)" }}>
                  exit <code>{returncode}</code>
                </span>
              )}
            </div>
            {jobMeta.error_message && (
              <>
                <div className="kvk">Error</div>
                <div style={{ color: "var(--danger)", fontSize: 13 }}>{jobMeta.error_message}</div>
              </>
            )}
          </div>
        ) : (
          <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading job…</p>
        )}
        {err && <p style={{ color: "var(--danger)", marginTop: 12, marginBottom: 0, fontSize: 13 }}>{err}</p>}
      </section>

      {/* ── Live progress (collapsible, auto-collapses when terminal) ── */}
      <details
        className="panel job-progress-collapse"
        open={progressOpen}
        onToggle={(e) => setProgressOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary className="job-progress-collapse-summary">
          <span className="section-title" style={{ margin: 0 }}>Progress</span>
          {jobTerminal && (
            <span className={`badge ${jobFinishedOk ? "ok" : "fail"}`} style={{ marginLeft: 10, fontSize: 10 }}>
              {jobFinishedOk ? "Complete" : "Failed"}
            </span>
          )}
          {!jobTerminal && phase && (
            <span style={{ marginLeft: 10, fontSize: 11, color: "var(--text-secondary)" }}>
              {phase} {tcur ? `@ t=${tcur}` : ""}
            </span>
          )}
        </summary>
        <div className="job-progress-collapse-body">
          <div className="kvs">
            <div className="kvk">WebSocket</div>
            <div><code>{live ? "connected" : "disconnected"}</code></div>
            <div className="kvk">Job status</div>
            <div><code>{jobStatus ?? "(unknown)"}</code></div>
            <div className="kvk">Phase</div>
            <div><code>{phase ?? "(not detected)"}</code></div>
            <div className="kvk">Solver time</div>
            <div><code>{tcur ?? "(n/a)"}</code></div>
            <div className="kvk">Progress</div>
            <div>
              <div className={`progress-track${progressIndeterminate ? " progress-track--indeterminate" : ""}`}>
                {!progressIndeterminate && (
                  <div
                    className={`progress-fill${jobStatus === "failed" ? " progress-fill--fail" : ""}`}
                    style={{ width: `${progressFillPct}%` }}
                  />
                )}
              </div>
              <small className="hint">{progressHint}</small>
            </div>
          </div>

          <div className="job-pipeline" aria-label="Job pipeline steps">
            <div className="job-pipeline-title">Steps</div>
            <ol className="job-pipeline-list">
              {pipelineWithStatus.map(({ step, status }) => (
                <li
                  key={step.key}
                  className={`job-pipeline-item job-pipeline-item--${status}`}
                  aria-current={status === "active" ? "step" : undefined}
                >
                  <span className="job-pipeline-ic" aria-hidden>
                    {status === "done" && "✓"}
                    {status === "active" && "●"}
                    {status === "pending" && "○"}
                    {status === "failed" && "✗"}
                    {status === "skipped" && "—"}
                  </span>
                  <span className="job-pipeline-label">{step.label}</span>
                  <span className="job-pipeline-badge">{pipelineStatusLabel(status)}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </details>

      {/* ── 3D viewer (only after job completed successfully and VTK exists) ── */}
      <section id="simulation-vtk" className="panel">
        <div className="panel-header" style={{ marginBottom: 10 }}>
          <div className="section-title" style={{ margin: 0 }}>3D visualization</div>
          {showViz && jobId && (
            <Link
              href={`/jobs/${jobId}/view`}
              className="fs-enter-btn"
              title="Open fullscreen simulation view"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
              <span>Fullscreen</span>
            </Link>
          )}
        </div>
        {!jobFinishedOk && (
          <p className="viewer-banner viewer-banner--info" style={{ marginBottom: 10 }}>
            The interactive viewer loads here only after the job finishes successfully (exit code 0). Use
            Progress above while the job runs; open <strong>Commands &amp; log</strong> at the bottom for full output.
          </p>
        )}
        {jobFinishedOk && outputs && !outputs.has_vtk && (
          <p className="viewer-banner viewer-banner--warn" style={{ marginBottom: 10 }}>
            The solver finished successfully (exit code 0), but this app&apos;s 3D view needs VTK files under{" "}
            <code>case/VTK/</code>, which are produced by <code>foamToVTK</code>. Add{" "}
            <code>&amp;&amp; foamToVTK</code> to the end of your template commands (or re-create the simulation so
            defaults include it), run again, then reload this page.
          </p>
        )}
        {showViz && jobId && canvasSrc ? (
          <div className="viewer-vtk-layout">
            <div className="viewer-vtk-stack">
              {trameSnap && local && (
                <div className="viewer-controls viewer-controls--linear">
                  <div className="vc-toolbar" role="toolbar" aria-label="VTK viewer controls">
                    <div className="vc-toolbar-group">
                      <label className="vc-label">Time</label>
                      <ForgeSelect
                        className="forge-select forge-select--toolbar"
                        value={local.time}
                        onChange={(v) => changeControl("time", v)}
                        disabled={!trameSnap.times.length}
                        options={
                          trameSnap.times.length
                            ? trameSnap.times.map((t) => ({ value: t, label: t }))
                            : [{ value: "", label: "(none)" }]
                        }
                        aria-label="Time"
                      />
                      <span className="vc-time-actions">
                        <button
                          type="button"
                          className="vc-btn-text vc-btn-text--compact"
                          onClick={() => sendCmd("prev")}
                          title="Previous saved time"
                        >
                          Prev
                        </button>
                        <button
                          type="button"
                          className="vc-btn-text vc-btn-text--compact"
                          onClick={() => sendCmd("next")}
                          title="Next saved time"
                        >
                          Next
                        </button>
                        <button
                          type="button"
                          className={`vc-btn-text vc-btn-text--compact ${trameSnap.playing ? "is-active" : ""}`}
                          onClick={() => sendCmd("toggle_play")}
                          title={trameSnap.playing ? "Pause" : "Play through times"}
                        >
                          {trameSnap.playing ? "Pause" : "Play"}
                        </button>
                        <ViewerPlaySpeedControl
                          valueSec={local.play_interval_sec}
                          disabled={!trameSnap.times.length}
                          onChangeSec={(v) => changeControl("play_interval_sec", v, false)}
                        />
                        {playStepMinGap != null && playStrideChoices.length > 0 && (
                          <span
                            className="vc-play-step-wrap"
                            title={`Play advances by this Δt each tick (multiples of smallest VTK gap ${formatPlayTimeStepLabel(playStepMinGap, playStepMinGap)})`}
                          >
                            <label className="vc-label">Step</label>
                            <ForgeSelect
                              className="forge-select forge-select--toolbar forge-select--play-step"
                              value={String(
                                playTimeStepChoiceIndex(playStrideChoices, local.play_stride),
                              )}
                              onChange={(v) => {
                                const i = parseInt(v, 10);
                                const stride = playStrideChoices[i];
                                if (stride == null || stride <= 0) return;
                                changeControl("play_stride", stride, false);
                              }}
                              disabled={!trameSnap.times.length}
                              options={playStrideChoices.map((c, i) => ({
                                value: String(i),
                                label: formatPlayTimeStepLabel(c, playStepMinGap),
                              }))}
                              aria-label="Play time step in simulation units"
                            />
                          </span>
                        )}
                      </span>
                    </div>
                    <span className="vc-toolbar-rule" aria-hidden />
                    {trameSnap.regions.length > 0 && (
                      <>
                        <div className="vc-toolbar-group">
                          <label className="vc-label">Region</label>
                          <ForgeSelect
                            className="forge-select forge-select--toolbar"
                            value={local.region}
                            onChange={(v) => changeControl("region", v)}
                            options={trameSnap.regions.map((r) => ({
                              value: r,
                              label: r,
                            }))}
                            aria-label="Region"
                          />
                        </div>
                        <span className="vc-toolbar-rule" aria-hidden />
                      </>
                    )}
                    <div className="vc-toolbar-group">
                      <label className="vc-label">File</label>
                      <ForgeSelect
                        className="forge-select forge-select--toolbar"
                        value={local.file}
                        onChange={(v) => changeControl("file", v)}
                        disabled={!trameSnap.files.length}
                        options={
                          trameSnap.files.length
                            ? trameSnap.files.map((f) => ({ value: f, label: f }))
                            : [{ value: "", label: "(none)" }]
                        }
                        aria-label="VTK file"
                      />
                    </div>
                    <span className="vc-toolbar-rule" aria-hidden />
                    <div className="vc-toolbar-group">
                      <label className="vc-label">Color</label>
                      <ForgeSelect
                        className="forge-select forge-select--toolbar"
                        value={local.scalar}
                        onChange={(v) => changeControl("scalar", v)}
                        options={trameSnap.scalars.map((s) => ({
                          value: s,
                          label: s,
                        }))}
                        aria-label="Scalar color"
                      />
                    </div>
                    <span className="vc-toolbar-rule" aria-hidden />
                    <div className="vc-toolbar-group">
                      <label className="vc-toggle vc-toggle--toolbar">
                        <input
                          type="checkbox"
                          checked={local.show_streamlines}
                          onChange={(e) => changeControl("show_streamlines", e.target.checked)}
                        />
                        Streamlines
                      </label>
                      <button type="button" className="vc-btn vc-btn--toolbar" onClick={() => sendCmd("load")} title="Reload current view">
                        Load
                      </button>
                      <button type="button" className="vc-btn vc-btn--toolbar" onClick={() => sendCmd("refresh")} title="Re-scan VTK folder">
                        Refresh
                      </button>
                    </div>
                  </div>
                </div>
              )}
              {trameSnap && (
                <ViewerTimeRail
                  times={trameSnap.times}
                  currentTime={local?.time ?? trameSnap.time}
                  onSelectTime={selectTime}
                  disabled={!trameSnap.times.length}
                />
              )}

              <div className="viewer-canvas-wrap">
                <iframe
                  ref={viewerIframeRef}
                  name="forge-trame-canvas"
                  title="Forge VTK visualization"
                  src={canvasSrc}
                  className="viewer-canvas-iframe"
                  onLoad={() => {
                    const w = viewerIframeRef.current?.contentWindow;
                    if (!w || !jobId) return;
                    const payload = { type: "forge-trame-set-job" as const, jobId, autoLoad: true as const };
                    for (const ms of [80, 400, 1200, 2800]) {
                      window.setTimeout(() => postToTrameViewer(w, payload, trameFramePostMessageTarget()), ms);
                    }
                  }}
                />
                <div className="vc-canvas-overlay" aria-live="polite">
                  <span className="vc-overlay-text">
                    {trameSnap?.status?.trim()
                      ? trameSnap.status
                      : trameSnap
                        ? "Connected — waiting for scene"
                        : "Connecting…"}
                    {local && trameSnap && (
                      <>
                        {" · "}
                        t={local.time}
                        {" · "}
                        {local.file}
                        {trameSnap.playing ? " · playing" : ""}
                      </>
                    )}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      {/* ── Download full job workspace (includes case.foam for ParaView) ── */}
      <section className="panel">
        <div className="section-title">Results</div>
        {jobId ? (
          <div className="results-log-toolbar">
            <span className="results-log-toolbar-label">Log tools:</span>
            <LogToolbar
              logText={log}
              jobId={jobId}
              jobMeta={
                jobMeta
                  ? {
                      status: jobStatus ?? jobMeta.status,
                      returncode,
                      error_message: jobMeta.error_message,
                      commands: jobMeta.commands,
                      simulation_id: jobMeta.simulation_id,
                    }
                  : null
              }
            />
          </div>
        ) : null}
        {jobId && (
          <JobResultFieldsPanel jobId={jobId} enabled={jobFinishedOk} />
        )}
        <p style={{ color: "var(--muted)", margin: "12px 0 12px", fontSize: 13, maxWidth: 520 }}>
          Download a ZIP of this job&apos;s workspace. A <code>case.foam</code> marker is added automatically so you can open the case in ParaView.
        </p>
        <a className="btn" href={download || "#"} download aria-disabled={!jobId}>
          Download results (ZIP)
        </a>
      </section>

      {/* ── Commands & full log (open when job finished or streaming) ── */}
      <details className="panel job-details-collapse">
        <summary className="job-details-collapse-summary">
          <span>Commands &amp; full log</span>
          {jobId ? (
            <span
              className="job-details-log-toolbar"
              role="presentation"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <LogToolbar
                logText={log}
                jobId={jobId}
                jobMeta={
                  jobMeta
                    ? {
                        status: jobStatus ?? jobMeta.status,
                        returncode,
                        error_message: jobMeta.error_message,
                        commands: jobMeta.commands,
                        simulation_id: jobMeta.simulation_id,
                      }
                    : null
                }
              />
            </span>
          ) : null}
        </summary>
        <div className="job-details-collapse-body">
          {jobMeta && (
            <>
              <div className="section-title" style={{ fontSize: 13, marginBottom: 8 }}>
                Commands (this job)
              </div>
              <pre className="log job-details-pre">{jobMeta.commands}</pre>
            </>
          )}
          <div className="section-title" style={{ fontSize: 13, margin: "16px 0 8px" }}>Full log</div>
          <pre className="log job-details-pre">{log || "(empty)"}</pre>
        </div>
      </details>

      <ChatBot
        pageContext="job"
        viewerState={viewerStateForAI}
        onViewerCmd={handleViewerCmd}
      />
    </>
  );
}
