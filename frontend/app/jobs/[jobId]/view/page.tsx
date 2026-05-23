"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchJob, fetchJobOutputs, type Job } from "@/lib/api";
import { postToTrameViewer, type TrameViewerSnapshot } from "@/lib/trameBridge";
import {
  trameCanvasViewerSrc,
  trameFramePostMessageTarget,
  trameOriginAcceptsMessage,
  tramePublicOrigin,
} from "@/lib/trame";
import { ViewerTimeRail } from "@/app/components/ViewerTimeRail";
import { ViewerPlaySpeedControl } from "@/app/components/ViewerPlaySpeedControl";
import { ForgeSelect } from "@/app/components/ui/ForgeSelect";
import {
  formatPlayTimeStepLabel,
  playTimeStepChoiceIndex,
  vtkPlayTimeStepChoices,
  vtkTimeMinGap,
} from "@/lib/vtkPlayTimeStep";

type LocalControls = {
  time: string;
  region: string;
  file: string;
  scalar: string;
  show_streamlines: boolean;
  play_interval_sec: number;
  play_stride: number;
};

const SNAP_SETTLE_MS = 600;

export default function JobFullscreenViewPage() {
  const params = useParams();
  const jobId = typeof params?.jobId === "string" ? params.jobId : Array.isArray(params?.jobId) ? params.jobId[0] : "";

  const [jobMeta, setJobMeta] = useState<Job | null>(null);
  const [outputs, setOutputs] = useState<{
    times: string[];
    regions: string[];
    has_vtk: boolean;
    has_foam: boolean;
  } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [canvasSrc, setCanvasSrc] = useState("");
  const viewerIframeRef = useRef<HTMLIFrameElement>(null);
  const [trameSnap, setTrameSnap] = useState<TrameViewerSnapshot | null>(null);
  const [local, setLocal] = useState<LocalControls | null>(null);
  const lastUserChange = useRef(0);
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const jobFinishedOk = jobMeta?.status === "completed" && jobMeta?.returncode === 0;
  const showViz = Boolean(jobFinishedOk && outputs?.has_vtk);
  const iframeEpoch = useRef(0);

  const WATCHDOG_MS = 12_000;
  const MAX_RETRIES = 3;
  const watchdogRetries = useRef(0);
  useEffect(() => {
    if (!canvasSrc || !showViz) { watchdogRetries.current = 0; return; }
    const tid = window.setTimeout(() => {
      if (trameSnap) return;
      if (watchdogRetries.current >= MAX_RETRIES) return;
      watchdogRetries.current += 1;
      iframeEpoch.current += 1;
      setCanvasSrc("");
      requestAnimationFrame(() =>
        setCanvasSrc(trameCanvasViewerSrc(jobId, window.location.origin)),
      );
    }, WATCHDOG_MS);
    return () => window.clearTimeout(tid);
  }, [canvasSrc, showViz, trameSnap, jobId]);

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      try {
        const [j, o] = await Promise.all([fetchJob(jobId), fetchJobOutputs(jobId)]);
        setJobMeta(j);
        setOutputs({ times: o.times, regions: o.regions, has_vtk: o.has_vtk, has_foam: o.has_foam });
        if (j.status === "completed" && j.returncode === 0 && o.has_vtk) {
          setCanvasSrc(trameCanvasViewerSrc(jobId, window.location.origin));
        } else {
          setCanvasSrc("");
        }
      } catch (e) {
        setLoadErr(e instanceof Error ? e.message : "Failed to load job");
      } finally {
        setInitialized(true);
      }
    })();
  }, [jobId]);

  useEffect(() => {
    if (!trameSnap) {
      setLocal(null);
      return;
    }
    const elapsed = Date.now() - lastUserChange.current;
    if (elapsed < SNAP_SETTLE_MS) return;
    setLocal({
      time: trameSnap.time,
      region: trameSnap.region,
      file: trameSnap.file,
      scalar: trameSnap.scalar,
      show_streamlines: trameSnap.show_streamlines,
      play_interval_sec: Number(trameSnap.play_interval_sec) || 0,
      play_stride: Number(trameSnap.play_stride) || 0,
    });
    setLastUpdate(Date.now());
  }, [trameSnap]);

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

  const enterBrowserFullscreen = () => {
    const el = rootRef.current;
    if (!el) return;
    void el.requestFullscreen?.().catch(() => {});
  };

  const timeLabel = useMemo(() => {
    if (!lastUpdate) return "—";
    return new Date(lastUpdate).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }, [lastUpdate]);

  const playStrideChoices = useMemo(
    () => vtkPlayTimeStepChoices(trameSnap?.times ?? []),
    [trameSnap?.times],
  );
  const playStepMinGap = useMemo(() => vtkTimeMinGap(trameSnap?.times ?? []), [trameSnap?.times]);

  if (!jobId) {
    return <div className="fs-sim-root fs-sim-root--center"><p>Invalid job.</p></div>;
  }

  if (!initialized) {
    return (
      <div className="fs-sim-root fs-sim-root--center">
        <p style={{ color: "var(--muted)" }}>Loading viewer…</p>
      </div>
    );
  }

  if (loadErr) {
    return (
      <div className="fs-sim-root fs-sim-root--center">
        <p style={{ color: "var(--danger)" }}>{loadErr}</p>
        <Link href={`/jobs/${jobId}`} className="btn secondary" style={{ marginTop: 12 }}>Back to job</Link>
      </div>
    );
  }

  if (!showViz || !canvasSrc) {
    return (
      <div className="fs-sim-root fs-sim-root--center">
        <p style={{ color: "var(--text-secondary)", maxWidth: 420, textAlign: "center" }}>
          Fullscreen view is available only after the job completes successfully and VTK output exists.
        </p>
        <Link href={`/jobs/${jobId}`} className="btn" style={{ marginTop: 16 }}>Back to job</Link>
      </div>
    );
  }

  return (
    <div ref={rootRef} className="fs-sim-root">
      <header className="fs-sim-topbar">
        <div className="fs-sim-topbar-left">
          <Link href={`/jobs/${jobId}`} className="fs-sim-back" title="Back to job">
            ← Job
          </Link>
          {jobMeta?.run_instruction_name && (
            <span className="fs-sim-title">{jobMeta.run_instruction_name}</span>
          )}
        </div>
        <div className="fs-sim-topbar-actions">
          <button type="button" className="fs-sim-icon-btn" onClick={enterBrowserFullscreen} title="Browser fullscreen">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
            </svg>
          </button>
        </div>
      </header>

      {/* Same stack as job page: one bordered card, linear toolbar, flex-height canvas */}
      <div className="fs-sim-viewer-body">
        <div className="viewer-vtk-layout viewer-vtk-layout--fs">
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
                        compact
                      />
                      {playStepMinGap != null && playStrideChoices.length > 0 && (
                        <span
                          className="vc-play-step-wrap"
                          title={`Δt per play tick (multiples of min VTK gap ${formatPlayTimeStepLabel(playStepMinGap, playStepMinGap)})`}
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
                            aria-label="Play time step"
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
                    <button type="button" className="vc-btn vc-btn--toolbar" onClick={() => sendCmd("load")}>Load</button>
                    <button type="button" className="vc-btn vc-btn--toolbar" onClick={() => sendCmd("refresh")}>Refresh</button>
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
                compact
              />
            )}

            <div className="viewer-canvas-wrap viewer-canvas-wrap--fs">
              <iframe
                ref={viewerIframeRef}
                name="forge-trame-canvas-fs"
                title="Forge VTK visualization"
                src={canvasSrc}
                className="viewer-canvas-iframe viewer-canvas-iframe--fs"
                onLoad={() => {
                  const w = viewerIframeRef.current?.contentWindow;
                  if (!w || !jobId) return;
                  const payload = { type: "forge-trame-set-job" as const, jobId, autoLoad: true as const };
                  for (const ms of [80, 400, 1200, 2800]) {
                    window.setTimeout(() => postToTrameViewer(w, payload, trameFramePostMessageTarget()), ms);
                  }
                }}
              />
              <div className="vc-canvas-overlay vc-canvas-overlay--fs" aria-live="polite">
                <span className="vc-overlay-text">
                  {trameSnap?.status?.trim() || (trameSnap ? "—" : "Connecting…")}
                  {trameSnap && (
                    <>
                      {" · "}
                      t={local?.time ?? trameSnap.time}
                      {" · "}
                      r={local?.region ?? trameSnap.region ?? "—"}
                      {" · "}
                      {local?.file ?? trameSnap.file ?? "—"}
                      {" · "}
                      {local?.scalar ?? trameSnap.scalar ?? "—"}
                      {" · "}
                      play {trameSnap.playing ? "on" : "off"}
                      {" · "}
                      sl {(local?.show_streamlines ?? trameSnap.show_streamlines) ? "on" : "off"}
                      {" · "}
                      delay {trameSnap.play_interval_sec ?? "—"}s
                      {" · "}
                      step{" "}
                      {playStepMinGap != null
                        ? formatPlayTimeStepLabel(Number(trameSnap.play_stride) || 0, playStepMinGap)
                        : "—"}
                      {" · "}
                      {trameSnap.times?.length ?? 0}/{trameSnap.files?.length ?? 0} steps/files
                      {" · "}
                      sync {timeLabel}
                    </>
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
