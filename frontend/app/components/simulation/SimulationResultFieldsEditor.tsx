"use client";

import type { SimulationResultField } from "@/lib/api";
import { SimulationInputFieldsEditor } from "@/app/components/simulation/SimulationInputFieldsEditor";

type Props = {
  fields: SimulationResultField[];
  onChange: (fields: SimulationResultField[]) => void;
};

/** Edit stored result field definitions (same editor as input fields). */
export function SimulationResultFieldsEditor({ fields, onChange }: Props) {
  return (
    <>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 16px" }}>
        These values are read from the completed job case after a successful run.
      </p>
      <SimulationInputFieldsEditor fields={fields} onChange={onChange} />
    </>
  );
}
