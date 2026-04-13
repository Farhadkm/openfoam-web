/** Play step = simulation-time advance per tick; options follow VTK output spacing only. */

function parseTimeValues(times: string[]): number[] {
  return times.map((t) => parseFloat(t)).filter((n) => Number.isFinite(n));
}

/** Smallest positive gap between consecutive VTK times (sorted). */
export function vtkTimeMinGap(times: string[]): number | null {
  const nums = [...parseTimeValues(times)].sort((a, b) => a - b);
  if (nums.length < 2) return null;
  let mg = Infinity;
  for (let i = 0; i < nums.length - 1; i++) {
    const g = nums[i + 1]! - nums[i]!;
    if (g > 1e-30) mg = Math.min(mg, g);
  }
  return Number.isFinite(mg) && mg > 0 ? mg : null;
}

/**
 * Allowed play steps: multiples of the minimum VTK time gap (1×, 2×, 3×, …),
 * same cadence as the viewer server — no arbitrary 0.1 grid.
 */
export function vtkPlayTimeStepChoices(times: string[]): number[] {
  const mg = vtkTimeMinGap(times);
  if (mg == null) return [];
  const nums = [...parseTimeValues(times)].sort((a, b) => a - b);
  const span = nums[nums.length - 1]! - nums[0]!;
  const mults = [1, 2, 3, 5, 10, 20, 50, 100];
  const set = new Set<number>();
  for (const m of mults) {
    const raw = m * mg;
    if (raw > 0 && raw <= span + mg * 0.5) {
      const steps = Math.round(raw / mg);
      set.add(Math.round(steps * mg * 1e12) / 1e12);
    }
  }
  set.add(mg);
  return Array.from(set).sort((a, b) => a - b);
}

/** Fewest decimals so `minGap` prints without noise; used for step labels. */
export function decimalsForMinGap(minGap: number): number {
  if (!Number.isFinite(minGap) || minGap <= 0) return 0;
  for (let d = 0; d <= 8; d++) {
    const rounded = Math.round(minGap * 10 ** d) / 10 ** d;
    if (Math.abs(rounded - minGap) <= 1e-9 * Math.max(minGap, 1)) return d;
  }
  return 8;
}

export function formatPlayTimeStepLabel(step: number, minGap: number | null): string {
  if (!Number.isFinite(step)) return "";
  if (minGap == null) return String(step);
  if (minGap < 1e-4 && minGap > 0) return step.toExponential(2);
  const d = decimalsForMinGap(minGap);
  return Number(step.toFixed(d)).toString();
}

export function nearestPlayTimeStep(value: number, choices: number[]): number {
  if (!choices.length) return Math.max(Number(value) || 0, 1e-12);
  const v = Number(value);
  if (!Number.isFinite(v) || v <= 0) return choices[0]!;
  return choices.reduce((best, c) => (Math.abs(c - v) < Math.abs(best - v) ? c : best));
}

export function playTimeStepChoiceIndex(choices: number[], value: number): number {
  const n = nearestPlayTimeStep(value, choices);
  const tol = 1e-6 * Math.max(Math.abs(n), Math.abs(choices[0] || 1), 1);
  const i = choices.findIndex((c) => Math.abs(c - n) <= tol);
  return i >= 0 ? i : 0;
}
