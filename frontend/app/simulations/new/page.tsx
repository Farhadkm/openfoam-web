"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  DiscoveredParametersPicker,
  type SelectedDiscoveredVar,
} from "@/app/components/simulation/DiscoveredParametersPicker";
import { SimulationWizardCaseFileStep } from "@/app/components/simulation/SimulationWizardCaseFileStep";
import { SimulationWizardDetailsStep } from "@/app/components/simulation/SimulationWizardDetailsStep";
import { WizardStepsBar } from "@/app/components/simulation/WizardStepsBar";
import { SIMULATION_WIZARD_LABELS } from "@/app/components/simulation/simulationWizardLabels";
import {
  analyzeResultZip,
  analyzeZip,
  createSimulation,
  type DiscoveredVariable,
  type SimulationInputField,
  type SimulationResultField,
  type ZipAnalysis,
} from "@/lib/api";
import { defaultCommandsFromZipAnalysis } from "@/lib/zipAnalysisCommands";

export default function NewSimulationPage() {
  const router = useRouter();

  const [engine, setEngine] = useState("openfoam");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [thumbnail, setThumbnail] = useState<File | null>(null);

  const [caseFile, setCaseFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<ZipAnalysis | null>(null);

  const [selected, setSelected] = useState<Map<string, SelectedDiscoveredVar>>(new Map());

  const [resultCaseFile, setResultCaseFile] = useState<File | null>(null);
  const [analyzingResult, setAnalyzingResult] = useState(false);
  const [resultAnalysis, setResultAnalysis] = useState<ZipAnalysis | null>(null);
  const [resultSelected, setResultSelected] = useState<Map<string, SelectedDiscoveredVar>>(new Map());
  const [resultExpandedDirs, setResultExpandedDirs] = useState<Set<string>>(new Set());

  const [commands, setCommands] = useState("");
  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());

  const toggleDir = (dir: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  const handleUpload = async (file: File) => {
    setCaseFile(file);
    setAnalyzing(true);
    setAnalysis(null);
    setError(null);
    setSelected(new Map());
    try {
      const result = await analyzeZip(file);
      setAnalysis(result);
      setCommands(defaultCommandsFromZipAnalysis(result));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze ZIP");
    } finally {
      setAnalyzing(false);
    }
  };

  const varKey = (v: DiscoveredVariable) => `${v.file}::${v.key}`;

  const toggleVar = (v: DiscoveredVariable) => {
    setSelected((prev) => {
      const next = new Map(prev);
      const k = varKey(v);
      if (next.has(k)) {
        next.delete(k);
      } else {
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
  };

  const updateVar = (k: string, patch: Partial<SelectedDiscoveredVar>) => {
    setSelected((prev) => {
      const next = new Map(prev);
      const cur = next.get(k);
      if (cur) next.set(k, { ...cur, ...patch });
      return next;
    });
  };

  const handleCreate = async () => {
    if (!caseFile) return;
    setCreating(true);
    setError(null);
    try {
      const inputFields: SimulationInputField[] = Array.from(selected.values()).map((v) => ({
        key: `${v.file}::${v.key}`,
        label: v.label,
        type: v.fieldType,
        default: v.value,
        ...(v.min ? { min: v.min } : {}),
        ...(v.max ? { max: v.max } : {}),
      }));
      const resultFields: SimulationResultField[] = Array.from(resultSelected.values()).map((v) => ({
        key: `${v.file}::${v.key}`,
        label: v.label,
        type: v.fieldType,
        default: v.value,
      }));
      await createSimulation({
        title: title.trim(),
        description: description.trim(),
        commands: commands.trim(),
        input_fields: inputFields,
        result_fields: resultFields,
        case_zip: caseFile,
        result_zip: resultCaseFile ?? undefined,
        thumbnail: thumbnail ?? undefined,
      });
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create simulation");
    } finally {
      setCreating(false);
    }
  };

  const handleResultUpload = async (file: File) => {
    setResultCaseFile(file);
    setAnalyzingResult(true);
    setResultAnalysis(null);
    setResultSelected(new Map());
    try {
      const result = await analyzeResultZip(file);
      setResultAnalysis(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze result ZIP");
    } finally {
      setAnalyzingResult(false);
    }
  };

  const resultVarKey = (v: DiscoveredVariable) => `${v.file}::${v.key}`;

  const toggleResultVar = (v: DiscoveredVariable) => {
    setResultSelected((prev) => {
      const next = new Map(prev);
      const k = resultVarKey(v);
      if (next.has(k)) {
        next.delete(k);
      } else {
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
  };

  const updateResultVar = (k: string, patch: Partial<SelectedDiscoveredVar>) => {
    setResultSelected((prev) => {
      const next = new Map(prev);
      const cur = next.get(k);
      if (cur) next.set(k, { ...cur, ...patch });
      return next;
    });
  };

  const toggleResultDir = (dir: string) => {
    setResultExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) next.delete(dir);
      else next.add(dir);
      return next;
    });
  };

  const canGoStep2 = title.trim().length > 0;
  const canGoStep3 = !!analysis && commands.trim().length > 0;
  const canGoStep4 = true;
  const canGoStep5 = true;

  return (
    <>
      <div className="page-desc">
        Create a new simulation template by uploading an CFD case and configuring adjustable
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
          thumbnail={thumbnail}
          remotePreviewUrl={null}
          onTitle={setTitle}
          onDescription={setDescription}
          onThumbnail={setThumbnail}
          engine={engine}
          onEngine={setEngine}
          aiContextTitle={title}
          aiContextDescription={description}
          thumbnailLabel="Thumbnail Image (optional)"
          footer={
            <div className="wizard-nav" style={{ marginTop: 16 }}>
              <span />
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
          zipInputId="case-zip"
          zipLabel="Case ZIP"
          zipRequired
          hint="ZIP containing system/, constant/, and initial condition directories."
          onZipSelected={(f) => void handleUpload(f)}
          analyzing={analyzing}
          analysis={analysis}
          expandedDirs={expandedDirs}
          onToggleDir={toggleDir}
          commands={commands}
          onCommandsChange={setCommands}
          showCommandsWithoutAnalysis={false}
          commandsTextareaRows={2}
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

      {step === 3 && analysis && (
        <section className="panel">
          <div className="panel-header">
            <div className="section-title" style={{ margin: 0 }}>Parameters</div>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>
              {selected.size} selected
            </span>
          </div>

          <DiscoveredParametersPicker
            analysis={analysis}
            selected={selected}
            onToggleVar={toggleVar}
            onUpdateVar={updateVar}
            varKey={varKey}
          />

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
          zipInputId="result-case-zip"
          zipLabel="Completed case ZIP"
          zipRequired={false}
          hint="Optional: upload a finished case so Forge can discover which outputs to show after runs."
          onZipSelected={(f) => void handleResultUpload(f)}
          selectedFileName={resultCaseFile?.name ?? null}
          onClearSelected={() => {
            setResultCaseFile(null);
            setResultAnalysis(null);
            setResultSelected(new Map());
          }}
          analyzing={analyzingResult}
          analysis={resultAnalysis}
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
              <button
                type="button"
                disabled={!canGoStep4}
                onClick={() => (resultAnalysis ? setStep(5) : void handleCreate())}
              >
                {resultAnalysis ? "Next: Result Fields" : "Create Simulation"}
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
              {resultSelected.size} selected
            </span>
          </div>

          {!resultAnalysis ? (
            <>
              <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
                No result case uploaded. You can create the simulation now or go back to upload one.
              </p>
              <div className="wizard-nav" style={{ marginTop: 24 }}>
                <button type="button" className="secondary" onClick={() => setStep(4)}>
                  Back
                </button>
                <button type="button" disabled={creating} onClick={() => void handleCreate()}>
                  {creating ? "Creating…" : "Create Simulation"}
                </button>
              </div>
            </>
          ) : (
            <>
              <DiscoveredParametersPicker
                analysis={resultAnalysis}
                selected={resultSelected}
                onToggleVar={toggleResultVar}
                onUpdateVar={updateResultVar}
                varKey={resultVarKey}
                mode="result"
              />
              <div className="wizard-nav" style={{ marginTop: 24 }}>
                <button type="button" className="secondary" onClick={() => setStep(4)}>
                  Back
                </button>
                <button type="button" disabled={creating || !canGoStep5} onClick={() => void handleCreate()}>
                  {creating ? "Creating…" : "Create Simulation"}
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}
