import type { SetupChecklist as SetupChecklistData } from "@followup/api-client-cuentas-claras";
import { SetupChecklistCard } from "@followup/app-shell";

import { checklistLabels } from "../lib/product";

interface SetupChecklistProps {
  checklist: SetupChecklistData;
  /** Show "Continuar configuración" while the wizard is unfinished. */
  wizardUnfinished: boolean;
}

export function SetupChecklist({ checklist, wizardUnfinished }: SetupChecklistProps) {
  return (
    <SetupChecklistCard
      checklist={checklist}
      labels={checklistLabels}
      wizardUnfinished={wizardUnfinished}
    />
  );
}
