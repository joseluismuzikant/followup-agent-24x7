import { Button, WizardStepper } from "@followup/ui";
import type { ReactNode } from "react";

export interface WizardFrameProps {
  productName: string;
  steps: readonly { id: string; label: string }[];
  current: string;
  /** Steps the person can jump to: completed ones and the current one. */
  reachable: readonly string[];
  onSelect: (id: string) => void;
  /** "Terminar después"; hidden when absent (before the business exists). */
  onFinishLater?: () => void;
  children: ReactNode;
}

/** The onboarding wizard's frame: "{product} · Paso N de M · {step}", the stepper and
 * "Terminar después". The steps' content is the product's. */
export function WizardFrame({
  productName,
  steps,
  current,
  reachable,
  onSelect,
  onFinishLater,
  children,
}: WizardFrameProps) {
  const index = steps.findIndex((step) => step.id === current);

  return (
    <div className="min-h-screen bg-muted/40">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm font-medium">
              {productName} · Paso {index + 1} de {steps.length} · {steps[index]?.label}
            </p>
            {onFinishLater ? (
              <Button variant="ghost" size="sm" onClick={onFinishLater}>
                Terminar después
              </Button>
            ) : null}
          </div>
          <WizardStepper
            ariaLabel="Pasos de la configuración"
            currentId={current}
            onSelect={onSelect}
            steps={steps.map((step) => ({
              id: step.id,
              label: step.label,
              reachable: reachable.includes(step.id),
            }))}
          />
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
    </div>
  );
}
