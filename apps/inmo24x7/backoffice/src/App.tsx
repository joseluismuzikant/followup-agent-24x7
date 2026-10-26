import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  PanelLayout,
} from "@inmo24x7/ui";
import { useQuery } from "@tanstack/react-query";

import { fetchTenants } from "./api/tenants";
import { TenantsTable } from "./components/tenants-table";

const navItems = [{ label: "Negocios", href: "/", active: true }];

export function App() {
  const tenantsQuery = useQuery({
    queryKey: ["tenants"],
    queryFn: fetchTenants,
  });

  return (
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
              Revisá que la API esté funcionando y volvé a intentarlo.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => void tenantsQuery.refetch()}>Reintentar</Button>
          </CardContent>
        </Card>
      ) : null}

      {tenantsQuery.isSuccess && tenantsQuery.data.length === 0 ? (
        <Card className="max-w-xl">
          <CardHeader>
            <CardTitle>Todavía no hay negocios</CardTitle>
            <CardDescription>
              Cuando se cree el primer cliente, va a aparecer acá.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {tenantsQuery.isSuccess && tenantsQuery.data.length > 0 ? (
        <Card>
          <CardContent>
            <TenantsTable tenants={tenantsQuery.data} />
          </CardContent>
        </Card>
      ) : null}
    </PanelLayout>
  );
}
