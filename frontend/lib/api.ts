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

/** Same shape as input fields; values are read from completed job case output. */
export type SimulationResultField = SimulationInputField;

export type Simulation = {
  id: string;
  title: string;
  description: string;
  commands: string;
  case_zip_path: string;
  thumbnail_url: string;
  input_fields: SimulationInputField[];
  result_fields: SimulationResultField[];
  has_result_zip: boolean;
  created_at: string;
  updated_at: string;
};

export type JobResultFieldValue = {
  key: string;
  label: string;
  type: string;
  value: string;
  error?: string;
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
  result_fields?: SimulationResultField[];
  case_zip: File;
  result_zip?: File;
  thumbnail?: File;
}) {
  const fd = new FormData();
  fd.append("title", data.title);
  fd.append("description", data.description);
  fd.append("commands", data.commands);
  fd.append("input_fields_json", JSON.stringify(data.input_fields));
  fd.append("result_fields_json", JSON.stringify(data.result_fields ?? []));
  fd.append("case_zip", data.case_zip);
  if (data.result_zip) fd.append("result_zip", data.result_zip);
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
    result_fields?: SimulationResultField[];
    thumbnail?: File;
    /** When set, replaces stored template case.zip on the server. */
    case_zip?: File;
    /** When set, replaces stored result case.zip on the server. */
    result_zip?: File;
  },
) {
  const fd = new FormData();
  if (data.title !== undefined) fd.append("title", data.title);
  if (data.description !== undefined) fd.append("description", data.description);
  if (data.commands !== undefined) fd.append("commands", data.commands);
  if (data.input_fields !== undefined)
    fd.append("input_fields_json", JSON.stringify(data.input_fields));
  if (data.result_fields !== undefined)
    fd.append("result_fields_json", JSON.stringify(data.result_fields));
  if (data.thumbnail) fd.append("thumbnail", data.thumbnail);
  if (data.case_zip) fd.append("case_zip", data.case_zip);
  if (data.result_zip) fd.append("result_zip", data.result_zip);
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

export type Conversation = {
  id: string;
  title: string;
  page_context: "run" | "job";
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type ConversationMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export async function fetchConversations() {
  const r = await fetch(`${base}/api/conversations`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ conversations: Conversation[] }>;
}

export async function createConversation(body?: {
  title?: string;
  page_context?: "run" | "job";
}) {
  const r = await fetch(`${base}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: body?.title ?? "",
      page_context: body?.page_context ?? "run",
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Conversation>;
}

export async function fetchConversation(id: string) {
  const r = await fetch(`${base}/api/conversations/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Conversation & { messages: ConversationMessage[] }>;
}

export async function deleteConversation(id: string) {
  const r = await fetch(`${base}/api/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: boolean; id: string }>;
}

export async function fetchConversationMessages(id: string) {
  const r = await fetch(`${base}/api/conversations/${encodeURIComponent(id)}/messages`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ conversation_id: string; messages: ConversationMessage[] }>;
}

export type TroubleshootRequest = {
  job_id: string;
  log: string;
  job: {
    status: string;
    returncode: number | null;
    error_message: string | null;
    commands?: string;
  };
  simulation?: {
    title: string;
    commands: string;
    input_fields: SimulationInputField[];
    result_fields: SimulationResultField[];
  } | null;
  inputs_applied?: Record<string, string> | null;
  fatal_hints?: string[];
};

export type TroubleshootResponse = {
  guide: string;
  job_id: string;
};

/** One-shot job log troubleshooting via CCS (no ICS routing). */
export async function requestJobTroubleshoot(body: TroubleshootRequest) {
  const r = await fetch(`${base}/api/ai/troubleshoot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const txt = await r.text();
    let msg = txt || "Troubleshooting failed";
    try {
      const j = JSON.parse(txt) as { detail?: string };
      if (typeof j.detail === "string" && j.detail) msg = j.detail;
    } catch {
      /* use raw */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<TroubleshootResponse>;
}

/** Ask CCS (via BFF) for a thumbnail; the server builds the image brief from title + description. */
export async function generateAiThumbnail(title: string, description: string) {
  const r = await fetch(`${base}/api/ai/generate-thumbnail`, {
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

export async function analyzeResultZip(file: File) {
  const fd = new FormData();
  fd.append("case_zip", file);
  const r = await fetch(`${base}/api/simulations/analyze-result-zip`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ZipAnalysis>;
}

/** Analyze the case.zip already stored for this simulation template (edit flow). */
// ── Mass run ──

export type MassRunInput = { label: string; value: string };

export type MassRunPreviewRun = {
  index: number;
  inputs: MassRunInput[];
};

export type MassRunPreview = {
  simulation_id: string;
  simulation_title: string;
  total_runs: number;
  field_labels: string[];
  runs: MassRunPreviewRun[];
};

export type MassRunRun = MassRunPreviewRun & {
  job_id?: string | null;
  status?: string;
  returncode?: number | null;
  error_message?: string | null;
};

export type MassRun = {
  id: string;
  simulation_id: string;
  simulation_title: string;
  batch_size: number;
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  runs: MassRunRun[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type MassRunListItem = Omit<MassRun, "runs">;

export async function previewMassRun(simId: string, csvFile: File) {
  const fd = new FormData();
  fd.append("csv_file", csvFile);
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/mass-run/preview`,
    { method: "POST", body: fd },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<MassRunPreview>;
}

export async function startMassRun(
  simId: string,
  body: { batch_size: number; runs: MassRunPreviewRun[] },
) {
  const r = await fetch(`${base}/api/simulations/${encodeURIComponent(simId)}/mass-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ id: string; status: string; total_runs: number }>;
}

export async function fetchMassRuns(simulationId?: string) {
  const q = simulationId
    ? `?simulation_id=${encodeURIComponent(simulationId)}`
    : "";
  const r = await fetch(`${base}/api/mass-runs${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ mass_runs: MassRunListItem[] }>;
}

export async function fetchMassRun(massRunId: string) {
  const r = await fetch(`${base}/api/mass-runs/${encodeURIComponent(massRunId)}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<MassRun>;
}

export function massRunDownloadUrl(massRunId: string) {
  return `${base}/api/mass-runs/${encodeURIComponent(massRunId)}/download`;
}

export function massRunResultsCsvUrl(massRunId: string) {
  return `${base}/api/mass-runs/${encodeURIComponent(massRunId)}/results.csv`;
}

// ── Simulation predictive model ──

export type PredictiveModelConfig = {
  simulation_id: string;
  training_mass_run_ids: string[];
  testing_mass_run_ids: string[];
  updated_at: string | null;
};

export async function fetchPredictiveModel(simId: string) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/predictive-model`,
    { cache: "no-store" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PredictiveModelConfig>;
}

export async function savePredictiveModel(
  simId: string,
  body: Pick<PredictiveModelConfig, "training_mass_run_ids" | "testing_mass_run_ids">,
) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/predictive-model`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PredictiveModelConfig>;
}

// ── PSS trained models (XGBoost) ──

export type PssModelMetrics = {
  per_target: Record<string, { rmse: number | null; mae: number | null; r2: number | null }>;
  aggregate: { rmse: number | null; mae: number | null; r2: number | null };
  note?: string;
};

export type PssTrainedModel = {
  id: string;
  simulation_id: string;
  technique: string;
  training_mass_run_ids: string[];
  testing_mass_run_ids: string[];
  feature_columns: string[];
  target_keys: string[];
  metrics: PssModelMetrics;
  n_train_rows: number;
  n_test_rows: number;
  created_at: string;
  summary_metrics?: { rmse: number | null; mae: number | null; r2: number | null };
};

export async function fetchPssModels(simId: string) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/predictive-models`,
    { cache: "no-store" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ simulation_id: string; models: PssTrainedModel[] }>;
}

export async function trainPssModel(
  simId: string,
  body?: {
    technique?: "xgboost";
    training_mass_run_ids?: string[];
    testing_mass_run_ids?: string[];
  },
) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/predictive-models/train`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ technique: "xgboost", ...body }),
    },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PssTrainedModel>;
}

export async function fetchPssModel(modelId: string) {
  const r = await fetch(`${base}/api/predictive-models/${encodeURIComponent(modelId)}`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<PssTrainedModel>;
}

export async function predictWithPssModel(modelId: string, inputs: Record<string, string>) {
  const r = await fetch(
    `${base}/api/predictive-models/${encodeURIComponent(modelId)}/predict`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs }),
    },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    model_id: string;
    simulation_id: string;
    predicted: boolean;
    fields: JobResultFieldValue[];
    values: Record<string, string>;
  }>;
}

export async function fetchSimulationTemplateAnalysis(simId: string) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/case-analysis`,
    { cache: "no-store" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ZipAnalysis>;
}

export async function fetchSimulationResultAnalysis(simId: string) {
  const r = await fetch(
    `${base}/api/simulations/${encodeURIComponent(simId)}/result-case-analysis`,
    { cache: "no-store" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ZipAnalysis>;
}

export async function fetchJobResultFields(jobId: string) {
  const r = await fetch(`${base}/api/jobs/${encodeURIComponent(jobId)}/result-fields`, {
    cache: "no-store",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ fields: JobResultFieldValue[] }>;
}
