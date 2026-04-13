"use client";

type Props = {
  labels: string[];
  /** 1-based current step index */
  currentStep: number;
};

export function WizardStepsBar({ labels, currentStep }: Props) {
  return (
    <div className="wizard-steps">
      {labels.map((label, i) => {
        const n = i + 1;
        return (
          <div
            key={label}
            className={`wizard-step ${currentStep === n ? "active" : currentStep > n ? "done" : ""}`}
          >
            <div className="wizard-step-num">{currentStep > n ? "✓" : n}</div>
            <span>{label}</span>
          </div>
        );
      })}
    </div>
  );
}
