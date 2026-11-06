import type { SetupChecklist as SetupChecklistData } from "@followup/api-client-inmo24x7";
import { SetupChecklistCard } from "@followup/app-shell";

const labels: Record<string, { label: string; href?: string }> = {
  account: { label: "Cuenta creada" },
  agent: { label: "Configurar tu agente", href: "/agente" },
  whatsapp: { label: "Conectar WhatsApp", href: "/onboarding" },
  properties: { label: "Cargar tus propiedades", href: "/propiedades" },
  meta: { label: "Verificar tu empresa en Meta" },
};

interface SetupChecklistProps {
  checklist: SetupChecklistData;
  /** Show "Continuar configuración" while the wizard is unfinished. */
  wizardUnfinished: boolean;
}

export function SetupChecklist({ checklist, wizardUnfinished }: SetupChecklistProps) {
  return (
    <SetupChecklistCard
      checklist={checklist}
      labels={labels}
      wizardUnfinished={wizardUnfinished}
    />
  );
}
