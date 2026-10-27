import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  PanelLayout,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchTenants } from "./api/tenants";
import { RequireAdmin } from "./components/RequireAdmin";
import { TenantsTable } from "./components/tenants-table";
import { apiErrorMessage } from "./lib/api-errors";

const PAGE_SIZE = 10;
const navItems = [{ label: "Negocios", href: "/", active: true }];

export function App() {
  const [page, setPage] = useState(1);
  const tenantsQuery = useQuery({
    queryKey: ["tenants", page, PAGE_SIZE],
    queryFn: () => fetchTenants(page, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Negocios"
        description="Clientes dados de alta en la plataforma."
        navItems={navItems}
        action={
          <Button
            variant="outline"
            onClick={() => void tenantsQuery.refetch()}
            disabled={tenantsQuery.isFetching}
          >
            {tenantsQuery.isFetching ? "Actualizando..." : "Actualizar"}
          </Button>
        }
      >
        {tenantsQuery.isPending ? (
          <p className="text-sm text-muted-foreground">Cargando negocios...</p>
        ) : null}

        {tenantsQuery.isError ? (
          <Card className="max-w-xl">
            <CardHeader>
              <CardTitle>No pudimos cargar los negocios</CardTitle>
              <CardDescription>
                {apiErrorMessage(
                  tenantsQuery.error,
                  "Revisá que la API esté funcionando y volvé a intentarlo.",
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => void tenantsQuery.refetch()}>Reintentar</Button>
            </CardContent>
          </Card>
        ) : null}

        {tenantsQuery.isSuccess && tenantsQuery.data.total === 0 ? (
          <Card className="max-w-xl">
            <CardHeader>
              <CardTitle>Todavía no hay negocios</CardTitle>
              <CardDescription>
                Cuando se cree el primer cliente, va a aparecer acá.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : null}

        {tenantsQuery.isSuccess && tenantsQuery.data.total > 0 ? (
          <Card>
            <CardContent>
              <TenantsTable tenants={tenantsQuery.data.items} />
              <div className="mt-4 flex flex-col gap-3 border-t pt-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <span>
                  Página {tenantsQuery.data.page} de {tenantsQuery.data.total_pages} ·{" "}
                  {tenantsQuery.data.total} negocios
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1 || tenantsQuery.isFetching}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={
                      page >= tenantsQuery.data.total_pages || tenantsQuery.isFetching
                    }
                    onClick={() => setPage((current) => current + 1)}
                  >
                    Siguiente
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </PanelLayout>
    </RequireAdmin>
  );
}
