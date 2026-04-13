import type { ZipAnalysis } from "@/lib/api";

/** Appends VTK export so the job viewer can load `case/VTK/` (Trame expects foamToVTK output). */
const VTK_EXPORT = " && foamToVTK";

/** Default shell commands inferred from a ZIP analysis (same rules as the new-simulation wizard). */
export function defaultCommandsFromZipAnalysis(result: ZipAnalysis): string {
  if (result.has_allrun) {
    return "chmod +x Allrun Allrun.pre Allclean 2>/dev/null || true; ./Allrun";
  }
  if (result.solver && result.has_blockmesh) {
    return `blockMesh && ${result.solver}${VTK_EXPORT}`;
  }
  if (result.solver) {
    return `${result.solver}${VTK_EXPORT}`;
  }
  return "";
}
