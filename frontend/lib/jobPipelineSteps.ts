/**
 * Derive human-readable pipeline steps from job shell commands and log lines.
 */

/** Longest names first for regex alternation. */
const OPENFOAM_KNOWN_COMMANDS = [
  "chtMultiRegionSimpleFoam",
  "chtMultiRegionFoam",
  "scalarTransportFoam",
  "surfaceFeatureExtract",
  "reconstructParMesh",
  "redistributeMeshPar",
  "splitMeshRegions",
  "snappyHexMesh",
  "potentialFoam",
  "simpleFoam",
  "pimpleFoam",
  "interFoam",
  "rhoPimpleFoam",
  "rhoSimpleFoam",
  "icoFoam",
  "mapFields",
  "setFields",
  "checkMesh",
  "createPatch",
  "decomposePar",
  "reconstructPar",
  "blockMesh",
  "topoSet",
  "foamToVTK",
  "PIMPLE",
];

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Ordered solver executables found in the job command string (bash). */
export function extractOrderedOpenFoamCommands(commands: string): string[] {
  if (!commands?.trim()) return [];
  const alt = [...OPENFOAM_KNOWN_COMMANDS].sort((a, b) => b.length - a.length).map(escapeRe).join("|");
  const re = new RegExp(`\\b(${alt})\\b`, "gi");
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(commands)) !== null) {
    const raw = m[1];
    const canonical = OPENFOAM_KNOWN_COMMANDS.find((c) => c.toLowerCase() === raw.toLowerCase()) ?? raw;
    out.push(canonical);
  }
  return out;
}

export type JobPipelineStepKind = "prepare" | "command" | "finalize";

export type JobPipelineStep = {
  key: string;
  label: string;
  kind: JobPipelineStepKind;
  /** Solver binary when kind === "command" (not set for generic placeholder). */
  command?: string;
};

export function buildJobPipelineSteps(commands: string): JobPipelineStep[] {
  const cmds = extractOrderedOpenFoamCommands(commands);
  const steps: JobPipelineStep[] = [
    { key: "prepare", label: "Prepare workspace & unpack case", kind: "prepare" },
  ];
  if (cmds.length === 0) {
    steps.push({
      key: "run-commands",
      label: "Run simulation commands",
      kind: "command",
    });
  } else {
    cmds.forEach((cmd, i) => {
      steps.push({
        key: `cmd-${cmd}-${i}`,
        label: `Run ${cmd}`,
        kind: "command",
        command: cmd,
      });
    });
  }
  steps.push({
    key: "finalize",
    label: "Finalize & write outputs",
    kind: "finalize",
  });
  return steps;
}

/** Ordered utilities/solvers seen in the log (`Running X on …`). */
export function parseRunningSequenceFromLog(log: string): string[] {
  const re = /^Running\s+(\S+)\s+on\s+/gm;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(log)) !== null) out.push(m[1]);
  return out;
}

export type StepDisplayStatus = "pending" | "active" | "done" | "failed" | "skipped";

export type JobStepWithStatus = {
  step: JobPipelineStep;
  status: StepDisplayStatus;
};

function commandStepStatus(
  ci: number,
  nCmd: number,
  runningSeq: string[],
  running: boolean,
  terminalOk: boolean,
  terminalFail: boolean,
  pending: boolean,
): StepDisplayStatus {
  const r = runningSeq.length;

  if (terminalOk) return "done";

  if (terminalFail) {
    if (nCmd === 0) return "failed";
    if (r === 0) return ci === 0 ? "failed" : "skipped";
    if (ci < r - 1) return "done";
    if (ci === r - 1) return "failed";
    return "skipped";
  }

  if (pending) return "pending";

  if (running) {
    if (r === 0) return ci === 0 ? "active" : "pending";
    if (ci < r - 1) return "done";
    if (ci === r - 1) return "active";
    return "pending";
  }

  return "pending";
}

export function computeJobStepStatuses(
  steps: JobPipelineStep[],
  ctx: {
    log: string;
    jobStatus: string | null;
    returncode: number | null;
  },
): JobStepWithStatus[] {
  const { log, jobStatus, returncode } = ctx;
  if (jobStatus == null) {
    return steps.map((step) => ({ step, status: "pending" as const }));
  }
  const runningSeq = parseRunningSequenceFromLog(log);
  const st = jobStatus;
  const terminalOk = st === "completed" && returncode === 0;
  const terminalFail = st === "failed" || (st === "completed" && returncode !== 0 && returncode != null);
  const running = st === "running";
  const pending = st === "pending";

  const cmdSteps = steps.filter((s) => s.kind === "command");
  const nCmd = cmdSteps.length;

  const out: JobStepWithStatus[] = [];

  for (const step of steps) {
    if (step.kind === "prepare") {
      const done =
        !pending || runningSeq.length > 0 || running || terminalOk || terminalFail;
      const active = pending && runningSeq.length === 0 && !running && !terminalOk && !terminalFail;
      out.push({ step, status: active ? "active" : done ? "done" : "pending" });
      continue;
    }

    if (step.kind === "finalize") {
      let status: StepDisplayStatus = "pending";
      if (terminalOk) status = "done";
      else if (terminalFail) status = "failed";
      out.push({ step, status });
      continue;
    }

    const ci = cmdSteps.indexOf(step);
    out.push({
      step,
      status: commandStepStatus(ci, nCmd, runningSeq, running, terminalOk, terminalFail, pending),
    });
  }

  return out;
}
