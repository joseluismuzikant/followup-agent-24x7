import type { SetupChecklist as SetupChecklistData } from "@followup/api-client-inmo24x7";
import { Button, ChecklistCard } from "@followup/ui";
import { Link, useNavigate } from "react-router";

import { resumeOnboarding } from "../lib/onboarding-deferred";

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
  const navigate = useNavigate();

  return (
    <ChecklistCard
      className="max-w-xl"
      title="Te falta poco para dejarlo completo"
      progressLabel={`${checklist.ready_count} de ${checklist.total} listos`}
      items={checklist.items.map((item) => ({
        key: item.key,
        done: item.done,
        label: labels[item.key]?.label ?? item.key,
        href: labels[item.key]?.href,
      }))}
      renderLink={(item, children) => (
        <Link to={item.href ?? "/"} className="text-primary underline-offset-4 hover:underline">
          {children}
        </Link>
      )}
      footer={
        wizardUnfinished ? (
          <Button
            variant="outline"
            className="self-start"
            onClick={() => {
              resumeOnboarding();
              navigate("/onboarding");
            }}
          >
            Continuar configuración
          </Button>
        ) : null
      }
    />
  );
}
