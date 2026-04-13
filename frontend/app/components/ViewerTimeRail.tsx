"use client";

import { useMemo } from "react";

type Props = {
  times: string[];
  currentTime: string;
  onSelectTime: (time: string) => void;
  disabled?: boolean;
  /** Tighter padding in fullscreen layout */
  compact?: boolean;
};

/** Discrete slider across VTK time folders (same ordering as the Time dropdown). */
export function ViewerTimeRail({ times, currentTime, onSelectTime, disabled, compact }: Props) {
  const n = times.length;
  const idx = useMemo(() => {
    if (!n) return 0;
    const i = times.indexOf(currentTime);
    return i >= 0 ? i : 0;
  }, [times, currentTime, n]);

  if (n <= 0) {
    return (
      <div className={`vc-time-rail vc-time-rail--empty${compact ? " vc-time-rail--compact" : ""}`}>
        <span className="vc-time-rail-empty-msg">
          No VTK time steps yet — run <code>foamToVTK</code>, then <strong>Refresh</strong> in the toolbar.
        </span>
      </div>
    );
  }

  const first = times[0] ?? "";
  const last = times[n - 1] ?? "";
  const sliderDisabled = Boolean(disabled) || n <= 1;

  return (
    <div className={`vc-time-rail${compact ? " vc-time-rail--compact" : ""}`}>
      <span className="vc-time-rail-end" title="First VTK time">
        {first}
      </span>
      <input
        type="range"
        className="vc-time-rail-slider"
        min={0}
        max={Math.max(0, n - 1)}
        step={1}
        value={idx}
        disabled={sliderDisabled}
        aria-label="VTK time along output timeline"
        aria-valuemin={0}
        aria-valuemax={Math.max(0, n - 1)}
        aria-valuenow={idx}
        aria-valuetext={`${currentTime} (${idx + 1} of ${n})`}
        onChange={(e) => {
          const j = parseInt(e.target.value, 10);
          const t = times[j];
          if (t != null) onSelectTime(t);
        }}
      />
      <span className="vc-time-rail-current" title="Current VTK time">
        {currentTime}
      </span>
      <span className="vc-time-rail-end" title="Last VTK time">
        {last}
      </span>
    </div>
  );
}
