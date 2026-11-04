import { Card, CardContent, CardHeader, CardTitle, PanelLayout } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router";

import { fetchPlans } from "../api/backoffice";
import { RequireAdmin } from "../components/RequireAdmin";
import { apiErrorMessage } from "../lib/api-errors";
import { navItems } from "../lib/nav";

const number = new Intl.NumberFormat("es-AR");

/** Planes (read-only for the MVP: no plan changes or billing yet). */
export function PlanesPage() {
  const location = useLocation();
  const query = useQuery({ queryKey: ["plans"], queryFn: fetchPlans });

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Planes"
        description="Los planes disponibles y cuántos negocios hay en cada uno."
        navItems={navItems(location.pathname)}
      >
        {query.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(query.error, "No pudimos cargar los planes.")}
          </p>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          {(query.data ?? []).map((plan) => (
            <Card key={plan.plan}>
              <CardHeader>
                <CardTitle>{plan.name}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-1 text-sm">
                <p>{number.format(plan.monthly_conversations)} conversaciones por mes</p>
                <p className="text-muted-foreground">
                  {plan.tenants} {plan.tenants === 1 ? "negocio" : "negocios"}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </PanelLayout>
    </RequireAdmin>
  );
}
