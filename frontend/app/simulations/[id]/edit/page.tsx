"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  DiscoveredParametersPicker,
  type SelectedDiscoveredVar,
} from "@/app/components/simulation/DiscoveredParametersPicker";
import { SimulationInputFieldsEditor } from "@/app/components/simulation/SimulationInputFieldsEditor";
import { SimulationResultFieldsEditor } from "@/app/components/simulation/SimulationResultFieldsEditor";
import { SimulationWizardCaseFileStep } from "@/app/components/simulation/SimulationWizardCaseFileStep";
import { SimulationWizardDetailsStep } from "@/app/components/simulation/SimulationWizardDetailsStep";
import { WizardStepsBar } from "@/app/components/simulation/WizardStepsBar";
import { SIMULATION_WIZARD_LABELS } from "@/app/components/simulation/simulationWizardLabels";
import {
  analyzeResultZip,
  analyzeZip,
  fetchSimulation,
  fetchSimulationResultAnalysis,
  fetchSimulationTemplateAnalysis,
  simulationThumbnailUrl,
  updateSimulation,
  type DiscoveredVariable,
  type Simulation,
  type SimulationInputField,
  type SimulationResultField,
  type ZipAnalysis,
} from "@/lib/api";
import { defaultCommandsFromZipAnalysis } from "@/lib/zipAnalysisCommands";

export default function EditSimulationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [sim, setSim] = useState<Simulation | null>(null);
  const [loading, setLoading] = useState(true);

  const [engine, setEngine] = useState("openfoam");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [thumbFile, setThumbFile] = useState<File | null>(null);
  const [commands, setCommands] = useState("");
  const [fields, setFields] = useState<SimulationInputField[]>([]);
  const [resultFields, setResultFields] = useState<SimulationResultField[]>([]);

  const [caseReplacement, setCaseReplacement] = useState<File | null>(null);
  const [resultReplacement, setResultReplacement] = useState<File | null>(null);
  const [analyzingResult, setAnalyzingResult] = useState(false);
  const [templateResultAnalysis, setTemplateResultAnalysis] = useState<ZipAnalysis | null>(null);
  const [replacementResultAnalysis, setReplacementResultAnalysis] = useState<ZipAnalysis | null>(null);
  const [loadingResultAnalysis, setLoadingResultAnalysis] = useState(false);
  const [resultExpandedDirs, setResultExpandedDirs] = useState<Set<string>>(new Set());
  const [resultSelected, setResultSelected] = useState<Map<string, SelectedDiscoveredVar>>(new Map());
  const [analyzing, setAnalyzing] = useState(false);
  /** Parsed from the ZIP already saved for this template (server). */
  const [templateZipAnalysis, setTemplateZipAnalysis] = useState<ZipAnalysis | null>(null);
  /** Parsed from an optional newly uploaded replacement ZIP. */
  const [replacementZipAnalysis, setReplacementZipAnalysis] = useState<ZipAnalysis | null>(null);
  const [loadingTemplateAnalysis, setLoadingTemplateAnalysis] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const displayZipAnalysis = replacementZipAnalysis ?? templateZipAnalysis;
  const displayResultAnalysis = replacementResultAnalysis ?? templateResultAnalysis;

  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setTemplateZipAnalysis(null);
    setReplacementZipAnalysis(null);
    setCaseReplacement(null);
    setTemplateResultAnalysis(null);
    setReplacementResultAnalysis(null);
    setResultReplacement(null);
    setResultSelected(new Map());
  }, [id]);

  useEffect(() => {
    fetchSimulation(id)
      .then((s) => {
        setSim(s);
        setTitle(s.title);
        setDescription(s.description);
        setCommands(typeof s.commands === "string" ? s.commands : "");
        setFields(
          (s.input_fields ?? []).map((raw) => ({
            key: String(raw.key ?? ""),
            label: String(raw.label ?? ""),
            type:
              raw.type === "number" || raw.type === "text" || raw.type === "select"
                ? raw.type
                : "text",
            default: raw.default != null ? String(raw.default) : "",
            min: raw.min != null ? String(raw.min) : undefined,
            max: raw.max != null ? String(raw.max) : undefined,
            options: raw.options,
          })),
        );
        setResultFields(
          (s.result_fields ?? []).map((raw) => ({
            key: String(raw.key ?? ""),
            label: String(raw.label ?? ""),
            type:
              raw.type === "number" || raw.type === "text" || raw.type === "select"
                ? raw.type
                : "text",
            default: raw.default != null ? String(raw.default) : "",
          })),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load simulation"))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id || !sim || sim.id !== id) return;
    let cancelled = false;
    setLoadingTemplateAnalysis(true);
    fetchSimulationTemplateAnalysis(id)
      .then((a) => {
        if (!cancelled) setTemplateZipAnalysis(a);
      })
      .catch(() => {
        if (!cancelled) setTemplateZipAnalysis(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingTemplateAnalysis(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, sim]);

  useEffect(() => {
    if (!id || !sim?.has_result_zip) return;
    let cancelled = false;
    setLoadingResultAnalysis(true);
    fetchSimulationResultAnalysis(id)
      .then((a) => {
        if (!cancelled) setTemplateResultAnalysis(a);
      })
      .catch(() => {
        if (!cancelled) setTemplateResultAnalysis(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingResultAnalysis(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, sim?.has_result_zip]);

  const toggleDir = (dir: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  const handleCaseReplace = async (file: File) => {
    setCaseReplacement(file);
    setAnalyzing(true);
    setReplacementZipAnalysis(null);
    setError(null);
    try {
      const result = await analyzeZip(file);
      setReplacementZipAnalysis(result);
      setCommands(defaultCommandsFromZipAnalysis(result));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze ZIP");
      setCaseReplacement(null);
    } finally {
      setAnalyzing(false);
    }
  };

  const clearCaseReplacement = () => {
    setCaseReplacement(null);
    setReplacementZipAnalysis(null);
    if (sim) setCommands(typeof sim.commands === "string" ? sim.commands : "");
  };

  const handleResultReplace = async (file: File) => {
    setResultReplacement(file);
    setResultSelected(new Map());
    setAnalyzingResult(true);
    setReplacementResultAnalysis(null);
    setError(null);
    try {
      const result = await analyzeResultZip(file);
      setReplacementResultAnalysis(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze result ZIP");
      setResultReplacement(null);
    } finally {
      setAnalyzingResult(false);
    }
  };

  const clearResultReplacement = () => {
    setResultReplacement(null);
    setReplacementResultAnalysis(null);
  };

  const toggleResultDir = (dir: string) => {
    setResultExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  const resultVarKey = (v: DiscoveredVariable) => `${v.file}::${v.key}`;

  const mergeResultSelectedIntoFields = (): SimulationResultField[] => {
    const fromPicker = Array.from(resultSelected.values()).map((v) => ({
      key: `${v.file}::${v.key}`,
      label: v.label,
      type: v.fieldType,
      default: v.value,
    }));
    if (fromPicker.length === 0) return resultFields;
    const keys = new Set(fromPicker.map((f) => f.key));
    const kept = resultFields.filter((f) => !keys.has(f.key));
    return [...kept, ...fromPicker];
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateSimulation(id, {
        title: title.trim(),
        description: description.trim(),
        commands: commands.trim(),
        input_fields: fields,
        result_fields: mergeResultSelectedIntoFields(),
        thumbnail: thumbFile ?? undefined,
        ...(caseReplacement ? { case_zip: caseReplacement } : {}),
        ...(resultReplacement ? { result_zip: resultReplacement } : {}),
      });
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const canGoStep2 = title.trim().length > 0;
  const canGoStep3 = commands.trim().length > 0;

  const remoteThumb = sim?.thumbnail_url ? simulationThumbnailUrl(sim.id) : null;

  if (loading) {
    return (
      <div className="panel">
        <p style={{ color: "var(--muted)", margin: 0, fontSize: 13 }}>Loading simulation…</p>
      </div>
    );
  }

  if (!sim) {
    return (
      <div className="panel" style={{ borderColor: "var(--danger)" }}>
        <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>
          {error || "Simulation not found."}
        </p>
      </div>
    );
  }

  const commandsHintEdit =
    caseReplacement != null
      ? "Updated from the new ZIP — review before saving. Shell commands when running this simulation."
      : "Shell commands when running this simulation. Upload a new ZIP on this step to replace the template and refresh suggestions.";

  return (
    <>
      <div className="page-desc">
        Edit simulation template — same steps as creating a new one: details, case file, then
        parameters.
      </div>

      <WizardStepsBar labels={[...SIMULATION_WIZARD_LABELS]} currentStep={step} />

      {error && (
        <div className="panel" style={{ borderColor: "var(--danger)", marginBottom: 16 }}>
          <p style={{ color: "var(--danger)", margin: 0, fontSize: 13 }}>{error}</p>
        </div>
      )}

      {step === 1 && (
        <SimulationWizardDetailsStep
          title={title}
          description={description}
          thumbnail={thumbFile}
          remotePreviewUrl={remoteThumb}
          onTitle={setTitle}
          onDescription={setDescription}
          onThumbnail={setThumbFile}
          engine={engine}
          onEngine={setEngine}
          aiContextTitle={title}
          aiContextDescription={description}
          thumbnailLabel="Thumbnail Image"
          footer={
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => router.push("/")}>
                Cancel
              </button>
              <button type="button" disabled={!canGoStep2} onClick={() => setStep(2)}>
                Next: Upload Case
              </button>
            </div>
          }
        />
      )}

      {step === 2 && (
        <SimulationWizardCaseFileStep
          panelTitle="Upload Case File"
          zipInputId="edit-case-zip"
          zipLabel="Case ZIP"
          zipRequired={false}
          hint="Optional: upload a new ZIP to replace the stored template. Leave unchanged to keep the current case. Root should contain system/, constant/, and time directories (e.g. 0/)."
          onZipSelected={(f) => void handleCaseReplace(f)}
          selectedFileName={caseReplacement?.name ?? null}
          onClearSelected={clearCaseReplacement}
          analyzing={analyzing || loadingTemplateAnalysis}
          analysis={displayZipAnalysis}
          expandedDirs={expandedDirs}
          onToggleDir={toggleDir}
          commands={commands}
          onCommandsChange={setCommands}
          showCommandsWithoutAnalysis
          commandsTextareaRows={4}
          commandsHint={commandsHintEdit}
          footer={
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => setStep(1)}>
                Back
              </button>
              <button type="button" disabled={!canGoStep3} onClick={() => setStep(3)}>
                Next: Configure Parameters
              </button>
            </div>
          }
        />
      )}

      {step === 3 && (
        <section className="panel">
          <div className="panel-header">
            <div className="section-title" style={{ margin: 0 }}>Parameters</div>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {fields.length} parameter{fields.length !== 1 ? "s" : ""}
            </span>
          </div>

          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
            Edit adjustable fields stored on this template (keys, labels, defaults, and types).
          </p>

          <SimulationInputFieldsEditor fields={fields} onChange={setFields} />

          <div className="wizard-nav" style={{ marginTop: 24 }}>
            <button type="button" className="secondary" onClick={() => setStep(2)}>
              Back
            </button>
            <button type="button" onClick={() => setStep(4)}>
              Next: Result Case
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <SimulationWizardCaseFileStep
          panelTitle="Result Case (optional)"
          zipInputId="edit-result-case-zip"
          zipLabel="Completed case ZIP"
          zipRequired={false}
          hint="Optional: upload a finished case to discover result fields. Leave unchanged to keep the stored result case."
          onZipSelected={(f) => void handleResultReplace(f)}
          selectedFileName={resultReplacement?.name ?? null}
          onClearSelected={clearResultReplacement}
          analyzing={analyzingResult || loadingResultAnalysis}
          analysis={displayResultAnalysis}
          expandedDirs={resultExpandedDirs}
          onToggleDir={toggleResultDir}
          commands=""
          onCommandsChange={() => {}}
          showCommands={false}
          footer={
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => setStep(3)}>
                Back
              </button>
              <button type="button" onClick={() => setStep(5)}>
                Next: Result Fields
              </button>
            </div>
          }
        />
      )}

      {step === 5 && (
        <section className="panel">
          <div className="panel-header">
            <div className="section-title" style={{ margin: 0 }}>Result Fields</div>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {resultFields.length} stored · {resultSelected.size} from discovery
            </span>
          </div>

          {displayResultAnalysis ? (
            <DiscoveredParametersPicker
              analysis={displayResultAnalysis}
              selected={resultSelected}
              onToggleVar={(v) => {
                const k = resultVarKey(v);
                setResultSelected((prev) => {
                  const next = new Map(prev);
                  if (next.has(k)) next.delete(k);
                  else {
                    next.set(k, {
                      ...v,
                      label: v.key.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase()),
                      fieldType: v.type === "number" ? "number" : "text",
                      min: "",
                      max: "",
                    });
                  }
                  return next;
                });
              }}
              onUpdateVar={(k, patch) => {
                setResultSelected((prev) => {
                  const next = new Map(prev);
                  const cur = next.get(k);
                  if (cur) next.set(k, { ...cur, ...patch });
                  return next;
                });
              }}
              varKey={resultVarKey}
              mode="result"
            />
          ) : (
            <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
              No result case to analyze yet. Go back to <strong>Result Case</strong> and upload a
              completed case ZIP, or edit stored result fields manually below.
            </p>
          )}

          <SimulationResultFieldsEditor fields={resultFields} onChange={setResultFields} />

          <div className="wizard-nav" style={{ marginTop: 24 }}>
            <button type="button" className="secondary" onClick={() => setStep(4)}>
              Back
            </button>
            <button type="button" disabled={saving} onClick={() => void handleSave()}>
              {saving ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
