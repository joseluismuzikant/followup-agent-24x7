import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { fetchOnboarding } from "../api/onboarding";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { SetupChecklist } from "../components/SetupChecklist";

export function InicioPage() {
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });
  const whatsappQuery = useQuery({
    queryKey: ["whatsapp"],
    queryFn: fetchWhatsAppStatus,
    retry: false,
  });
  const whatsapp = whatsappQuery.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        {whatsapp?.status === "connected" ? (
          <Badge tone="success">
            Agente activo
            {whatsapp.display_phone_number ? ` · ${whatsapp.display_phone_number}` : ""}
          </Badge>
        ) : null}
        <Button asChild>
          <Link to="/probar">Probar el agente</Link>
        </Button>
      </div>
      {onboardingQuery.data ? (
        <SetupChecklist
          checklist={onboardingQuery.data.checklist}
          wizardUnfinished={!onboardingQuery.data.finished}
        />
      ) : null}
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Esta semana</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Todavía no hay consultas. Cuando lleguen, vas a ver acá cómo viene la semana.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
