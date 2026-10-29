import { cn } from "../lib/utils";

interface WizardStep {
  id: string;
  label: string;
  /** Steps the user can jump to: completed ones and the current one. */
  reachable: boolean;
}

interface WizardStepperProps {
  steps: readonly WizardStep[];
  currentId: string;
  onSelect: (id: string) => void;
  ariaLabel?: string;
  className?: string;
}

function WizardStepper({
  steps,
  currentId,
  onSelect,
  ariaLabel = "Progreso",
  className,
}: WizardStepperProps) {
  const currentIndex = steps.findIndex((step) => step.id === currentId);

  return (
    <nav aria-label={ariaLabel} data-slot="wizard-stepper" className={className}>
      <ol className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {steps.map((step, index) => {
          const isCurrent = step.id === currentId;
          const isPast = index < currentIndex;
          return (
            <li key={step.id}>
              <button
                type="button"
                disabled={!step.reachable}
                aria-current={isCurrent ? "step" : undefined}
                onClick={() => onSelect(step.id)}
                className={cn(
                  "flex items-center gap-2 rounded-md text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed",
                  isCurrent ? "font-semibold text-foreground" : "text-muted-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full border text-xs",
                    isCurrent && "border-primary bg-primary text-primary-foreground",
                    isPast && "border-primary text-primary",
                  )}
                >
                  {isPast ? "✓" : index + 1}
                </span>
                {step.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export { WizardStepper, type WizardStep };
