"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** Seconds — after rotation, low values sit at the bottom (fast), high at the top (slow). */
const SLIDER_MAX_SEC = 10;
const SLIDER_STEP = 0.05;

function formatDelay(sec: number): string {
  const s = Math.max(0, Number(sec) || 0);
  if (s === 0) return "0 s";
  return `${s.toFixed(2)} s`;
}

type Props = {
  valueSec: number;
  disabled?: boolean;
  onChangeSec: (sec: number) => void;
  compact?: boolean;
};

/**
 * Volume-style control: tap to open a popover with a vertical range + readout.
 * Controls play frame delay (seconds between VTK time steps after each load).
 */
export function ViewerPlaySpeedControl({ valueSec, disabled, onChangeSec, compact }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<{ cx: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setAnchor(null);
      return;
    }
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setAnchor({ cx: r.left + r.width / 2, top: r.top });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t)) return;
      if (popRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onReposition = () => {
      const el = wrapRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setAnchor({ cx: r.left + r.width / 2, top: r.top });
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("scroll", onReposition, true);
    window.addEventListener("resize", onReposition);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("scroll", onReposition, true);
      window.removeEventListener("resize", onReposition);
    };
  }, [open]);

  const sec = Math.max(0, Number(valueSec) || 0);
  const sliderVal = Math.min(SLIDER_MAX_SEC, sec);

  const popover =
    open && anchor && typeof document !== "undefined" ? (
      <div
        ref={popRef}
        className={`vc-play-speed-popover vc-play-speed-popover--fixed${compact ? " vc-play-speed--compact" : ""}`}
        role="dialog"
        aria-label="Frame delay while playing"
        style={{
          position: "fixed",
          left: anchor.cx,
          top: anchor.top,
          transform: "translate(-50%, calc(-100% - 6px))",
        }}
      >
        <div className="vc-play-speed-popover-inner">
          <div className="vc-play-speed-slider-wrap">
            <input
              type="range"
              className="vc-play-speed-range"
              min={0}
              max={SLIDER_MAX_SEC}
              step={SLIDER_STEP}
              value={sliderVal}
              disabled={disabled}
              aria-valuemin={0}
              aria-valuemax={SLIDER_MAX_SEC}
              aria-valuenow={sliderVal}
              aria-label="Delay in seconds"
              onChange={(e) => {
                onChangeSec(parseFloat(e.target.value));
              }}
            />
          </div>
          <span className="vc-play-speed-readout">{formatDelay(sec)}</span>
        </div>
      </div>
    ) : null;

  return (
    <div className={`vc-play-speed${compact ? " vc-play-speed--compact" : ""}`} ref={wrapRef}>
      <button
        type="button"
        className={`vc-btn-text vc-btn-text--compact vc-play-speed-trigger${open ? " is-active" : ""}`}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        title="Delay between frames while playing — click to adjust"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <span className="vc-play-speed-trigger-inner" aria-hidden>
          <svg className="vc-play-speed-ic" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
          </svg>
        </span>
        <span className="vc-play-speed-trigger-val">{formatDelay(sec)}</span>
      </button>
      {typeof document !== "undefined" && popover ? createPortal(popover, document.body) : null}
    </div>
  );
}
