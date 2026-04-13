"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ThemeConfirmDialog } from "@/app/components/ui/ThemeDialogs";
import {
  createJob,
  createRunInstruction,
  deleteRunInstruction,
  fetchRunInstructions,
  type RunInstruction,
} from "@/lib/api";
import JSZip from "jszip";

export default function SubmitPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [commands, setCommands] = useState("blockMesh && simpleFoam");
  const [zipTree, setZipTree] = useState<string>("");
  const [zipInsights, setZipInsights] = useState<Record<string, string>>({});
  const [runInstructions, setRunInstructions] = useState<RunInstruction[]>([]);
  const [selectedInstructionId, setSelectedInstructionId] = useState<string | null>(null);
  const [presetName, setPresetName] = useState("");
  const [presetBusy, setPresetBusy] = useState(false);
  const [confirmDeletePreset, setConfirmDeletePreset] = useState(false);

  const refreshInstructions = useCallback(async () => {
    try {
      const d = await fetchRunInstructions();
      setRunInstructions(d.run_instructions);
    } catch { setRunInstructions([]); }
  }, []);

  useEffect(() => { void refreshInstructions(); }, [refreshInstructions]);

  const analyzeZip = useCallback(async (f: File | null) => {
    setZipTree("");
    setZipInsights({});
    if (!f) return;
    try {
      const buf = await f.arrayBuffer();
      const zip = await JSZip.loadAsync(buf);
      const names = Object.keys(zip.files).filter((n) => !zip.files[n]?.dir);
      names.sort();

      const readSmall = async (p: string) => {
        const e = zip.file(p);
        if (!e) return null;
        const u8 = await e.async("uint8array");
        if (u8.byteLength > 200_000) return null;
        return new TextDecoder("utf-8", { fatal: false }).decode(u8);
      };

      const hasDir = (dir: string) => names.some((n) => n.startsWith(`${dir}/`));
      const controlDict = await readSmall("system/controlDict");
      const solver = controlDict?.match(/^\s*application\s+([A-Za-z0-9_+-]+)\s*;/m)?.[1] ?? "";
      const hasBlock = names.includes("system/blockMeshDict");
      const hasAllrun = names.includes("Allrun");

      setZipInsights({
        "Has system/": hasDir("system") ? "yes" : "no",
        "Has constant/": hasDir("constant") ? "yes" : "no",
        "Solver": solver || "(not found)",
        "Has Allrun": hasAllrun ? "yes" : "no",
      });

      const lines = names.slice(0, 100).map((n) => `  ${n}`);
      setZipTree(lines.join("\n"));

      if (commands === "blockMesh && simpleFoam") {
        if (hasAllrun) setCommands("chmod +x Allrun Allrun.pre Allclean 2>/dev/null || true; ./Allrun");
        else if (solver && hasBlock) setCommands(`blockMesh && ${solver}`);
      }
    } catch { /* ignore */ }
  }, [commands]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) { setError("Choose a ZIP of your OpenFOAM case."); return; }
    setLoading(true);
    setError(null);
    try {
      const result = await createJob(file, commands, selectedInstructionId ? { runInstructionId: selectedInstructionId } : undefined);
      router.push(`/jobs/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="page-desc">
        Upload an OpenFOAM case as a ZIP file and specify shell commands to run.
      </div>

      <section className="panel">
        <div className="section-title">Upload Case</div>
        <form onSubmit={onSubmit}>
          <label htmlFor="zip">Case ZIP</label>
          <input
            id="zip"
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              void analyzeZip(f);
            }}
          />
          <small className="hint">Zip the case folder with system/, constant/, and time directories.</small>

          {Object.keys(zipInsights).length > 0 && (
            <div className="mt-md">
              <div className="zipGrid">
                <div>
                  <label>ZIP Insights</label>
                  <div className="kvs" style={{ fontSize: 12 }}>
                    {Object.entries(zipInsights).map(([k, v]) => (
                      <div key={k} style={{ display: "contents" }}>
                        <div className="kvk">{k}</div>
                        <div><code>{v}</code></div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <label>Files</label>
                  <pre className="tree">{zipTree || "(reading…)"}</pre>
                </div>
              </div>
            </div>
          )}

          <div className="mt-md">
            <label htmlFor="preset">Run Instruction Preset</label>
            <select
              id="preset"
              value={selectedInstructionId ?? ""}
              onChange={(e) => {
                const id = e.target.value || null;
                setSelectedInstructionId(id);
                if (id) {
                  const p = runInstructions.find((x) => x.id === id);
                  if (p) setCommands(p.commands);
                }
              }}
            >
              <option value="">— None —</option>
              {runInstructions.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <div className="row mt-sm">
              <input
                type="text"
                placeholder="Name for new preset"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                style={{ flex: "1 1 10rem" }}
              />
              <button
                type="button"
                className="secondary sm"
                disabled={presetBusy || !presetName.trim()}
                onClick={async () => {
                  setPresetBusy(true);
                  try {
                    await createRunInstruction({ name: presetName.trim(), commands });
                    setPresetName("");
                    await refreshInstructions();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Could not save");
                  } finally { setPresetBusy(false); }
                }}
              >
                Save Preset
              </button>
              <button
                type="button"
                className="secondary sm"
                disabled={!selectedInstructionId}
                onClick={() => setConfirmDeletePreset(true)}
              >
                Delete
              </button>
            </div>
          </div>

          <label htmlFor="cmd" className="mt-md">Shell Commands</label>
          <textarea
            id="cmd"
            value={commands}
            onChange={(e) => setCommands(e.target.value)}
            spellCheck={false}
          />

          <div className="row mt-md">
            <button type="submit" disabled={loading}>
              {loading ? "Starting…" : "Run Simulation"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--danger)", marginTop: 12, fontSize: 13 }}>{error}</p>}
      </section>

      <ThemeConfirmDialog
        open={confirmDeletePreset}
        title="Delete preset"
        message="Delete this run-instruction preset? This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onCancel={() => setConfirmDeletePreset(false)}
        onConfirm={() => {
          const id = selectedInstructionId;
          setConfirmDeletePreset(false);
          if (!id) return;
          void (async () => {
            try {
              await deleteRunInstruction(id);
              setSelectedInstructionId(null);
              await refreshInstructions();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not delete");
            }
          })();
        }}
      />
    </>
  );
}
