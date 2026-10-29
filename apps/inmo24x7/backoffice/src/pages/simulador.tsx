import { Card, CardContent, PanelLayout } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useSearchParams } from "react-router";

import { fetchTenants } from "../api/tenants";
import { AdminSimulator } from "../components/AdminSimulator";
import { RequireAdmin } from "../components/RequireAdmin";
import { TenantPicker } from "../components/TenantPicker";
import { apiErrorMessage } from "../lib/api-errors";
import { navItems } from "../lib/nav";

/** The API caps a page at 100; search happens over that list. */
const PICKER_LIMIT = 100;

export function SimuladorPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const tenantId = searchParams.get("negocio");
  const tenantsQuery = useQuery({
    queryKey: ["tenants", 1, PICKER_LIMIT],
    queryFn: () => fetchTenants(1, PICKER_LIMIT),
  });

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Simulador"
        description="Probá el agente de un negocio como si fueras un cliente."
        navItems={navItems(location.pathname)}
      >
        <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <Card>
            <CardContent className="pt-6">
              {tenantsQuery.isError ? (
                <p className="text-sm text-destructive" role="alert">
                  {apiErrorMessage(tenantsQuery.error, "No pudimos cargar los negocios.")}
                </p>
              ) : (
                <TenantPicker
                  tenants={tenantsQuery.data?.items ?? []}
                  query={query}
                  onQueryChange={setQuery}
                  selectedId={tenantId}
                  onSelect={(id) => setSearchParams({ negocio: id })}
                />
              )}
            </CardContent>
          </Card>
          {tenantId ? (
            <AdminSimulator key={tenantId} tenantId={tenantId} />
          ) : (
            <p className="text-sm text-muted-foreground">
              Elegí un negocio para probar su agente.
            </p>
          )}
        </div>
      </PanelLayout>
    </RequireAdmin>
  );
}
