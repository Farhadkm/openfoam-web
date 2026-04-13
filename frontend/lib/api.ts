const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export function jobWsUrl(jobId: string) {
  const u = new URL(`${base}/api/jobs/${jobId}/ws`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

export function wsOrigin() {
  // Some websocket servers enforce origin checks; keep it explicit and consistent.
  return typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
}

export type Job = {
  id: string;
  status: string;
  commands: string;
  returncode: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  run_instruction_id?: string;
  run_instruction_name?: string;
  /** Present when this job was started from a simulation template. */
  simulation_id?: string;
};

export async function fetchJobs() {
  const r = await fetch(`${base}/api/jobs`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ jobs: Job[] }>;
}

export async function fetchJob(jobId: string) {
  const r = await fetch(`${base}/api/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Job>;
}

export type RunInstruction = {
  id: string;
  name: string;
  commands: string;
  description: string;
  created_at: string;
  updated_at: string;
};

export async function fetchRunInstructions() {
  const r = await fetch(`${base}/api/run-instructions`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ run_instructions: RunInstruction[] }>;
}

export async function createRunInstruction(body: { name: string; commands: string; description?: string }) {
  const r = await fetch(`${base}/api/run-instructions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: body.name,
      commands: body.commands,
      description: body.description ?? "",
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<RunInstruction>;
}

export async function deleteRunInstruction(id: string) {
  const r = await fetch(`${base}/api/run-instructions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: boolean; id: string }>;
}

export async function createJob(
  caseZip: File,
  commands: string,
  opts?: { runInstructionId?: string | null },
) {
  const fd = new FormData();
  fd.append("case_zip", caseZip);
  fd.append("commands", commands);
  if (opts?.runInstructionId) {
    fd.append("run_instruction_id", opts.runInstructionId);
  }
  const r = await fetch(`${base}/api/jobs`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ id: string; status: string }>;
}

export async function fetchJobLog(jobId: string) {
  const r = await fetch(`${base}/api/jobs/${jobId}/log`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ log: string }>;
}

/** Read a text file from the job case directory (e.g. `system/controlDict`). */
export async function fetchCaseFileText(jobId: string, pathUnderCase: string) {
  const path = pathUnderCase.split("/").map(encodeURIComponent).join("/");
  const r = await fetch(`${base}/api/jobs/${encodeURIComponent(jobId)}/case/${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.text();
}

export async function fetchJobOutputs(jobId: string) {
  const r = await fetch(`${base}/api/jobs/${jobId}/outputs`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    job_id: string;
    times: string[];
    regions: string[];
    has_vtk: boolean;
    has_foam: boolean;
  }>;
}

export function downloadUrl(jobId: string) {
  return `${base}/api/jobs/${jobId}/download`;
}

// ── Simulations ──

export type SimulationInputField = {
  key: string;
  label: string;
  type: "number" | "text" | "select";
  default: string;
  min?: string;
  max?: string;
  options?: string[];
};

export type Simulation = {
  id: string;
  title: string;
  description: string;
  commands: string;
  case_zip_path: string;
  thumbnail_url: string;
  input_fields: SimulationInputField[];
  created_at: string;
  updated_at: string;
};

export async function fetchSimulations() {
  const r = await fetch(`${base}/api/simulations`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ simulations: Simulation[] }>;
}

export async function fetchSimulation(id: string) {
  const r = await fetch(`${base}/api/simulations/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Simulation>;
}

export async function createSimulation(data: {
  title: string;
  description: string;
  commands: string;
  input_fields: SimulationInputField[];
  case_zip: File;
  thumbnail?: File;
}) {
  const fd = new FormData();
  fd.append("title", data.title);
  fd.append("description", data.description);
  fd.append("commands", data.commands);
  fd.append("input_fields_json", JSON.stringify(data.input_fields));
  fd.append("case_zip", data.case_zip);
  if (data.thumbnail) fd.append("thumbnail", data.thumbnail);
  const r = await fetch(`${base}/api/simulations`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Simulation>;
}

export async function runSimulation(simId: string, inputs?: Record<string, string>) {
  const r = await fetch(`${base}/api/simulations/${encodeURIComponent(simId)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs: inputs ?? {} }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ id: string; status: string; simulation_id: string }>;
}

export function simulationThumbnailUrl(simId: string) {
  return `${base}/api/simulations/${encodeURIComponent(simId)}/thumbnail`;
}

export async function updateSimulation(
  simId: string,
  data: {
    title?: string;
    description?: string;
    commands?: string;
    input_fields?: SimulationInputField[];
    thumbnail?: File;
    /** When set, replaces stored template case.zip on the server. */
    case_zip?: File;
  },
) {
  const fd = new FormData();
  if (data.title !== undefined) fd.append("title", data.title);
  if (data.description !== undefined) fd.append("description", data.description);
  if (data.commands !== undefined) fd.append("commands", data.commands);
  if (data.input_fields !== undefined)
    fd.append("input_fields_json", JSON.stringify(data.input_fields));
  if (data.thumbnail) fd.append("thumbnail", data.thumbnail);
  if (data.case_zip) fd.append("case_zip", data.case_zip);
  const r = await fetch(`${base}/api/simulations/${encodeURIComponent(simId)}`, {
    method: "PATCH",
    body: fd,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Simulation>;
}

export async function deleteSimulation(simId: string) {
  const r = await fetch(`${base}/api/simulations/${encodeURIComponent(simId)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: boolean; id: string }>;
}

const aiBase =
  (typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_AI_WS_URL?.replace(/^ws/, "http")?.replace(/\/ws\/?$/, "")
    : null) || "http://localhost:8081";

/** Ask the AI service for a thumbnail; the server builds the image brief from title + description. */
export async function generateAiThumbnail(title: string, description: string) {
  const r = await fetch(`${aiBase}/generate-thumbnail`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim(), description: description.trim() }),
  });
  if (!r.ok) {
    const txt = await r.text();
    let msg = txt || "Failed to generate thumbnail";
    try {
      const j = JSON.parse(txt) as { error?: string };
      if (typeof j.error === "string" && j.error) msg = j.error;
    } catch {
      /* use raw body */
    }
    throw new Error(msg);
  }
  const blob = await r.blob();
  if (!blob.type.startsWith("image/")) {
    const errTxt = await blob.text();
    try {
      const j = JSON.parse(errTxt) as { error?: string };
      if (j?.error) throw new Error(j.error);
    } catch {
      /* fall through */
    }
    throw new Error("AI service did not return an image.");
  }
  return new File([blob], "thumbnail.png", { type: blob.type || "image/png" });
}

export type DiscoveredVariable = {
  file: string;
  key: string;
  value: string;
  type: "number" | "text";
};

export type ZipAnalysis = {
  solver: string;
  has_allrun: boolean;
  has_blockmesh: boolean;
  file_count: number;
  structure: Record<string, string[]>;
  discovered_variables: DiscoveredVariable[];
};

export async function analyzeZip(file: File) {
  const fd = new FormData();
  fd.append("case_zip", file);
  const r = await fetch(`${base}/api/simulations/analyze-zip`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ZipAnalysis>;
}

/** Analyze the case.zip already stored for this simulation template (edit flow). */
export async function fetchSimulationTemplateAnalysis(simId: string) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/case-analysis`,
    { cache: "no-store" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ZipAnalysis>;
}
