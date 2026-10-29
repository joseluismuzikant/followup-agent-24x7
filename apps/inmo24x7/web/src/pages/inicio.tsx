import { Button, Card, CardContent, CardHeader, CardTitle } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { fetchOnboarding } from "../api/onboarding";
import { SetupChecklist } from "../components/SetupChecklist";

export function InicioPage() {
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
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
