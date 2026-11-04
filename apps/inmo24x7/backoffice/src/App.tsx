import type { BusinessFilter } from "@followup/api-client-inmo24x7";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  KpiCard,
  Pagination,
  PanelLayout,
  SegmentedControl,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router";

import { fetchBusinesses } from "./api/backoffice";
import { CreateBusinessDialog } from "./components/CreateBusinessDialog";
import { RequireAdmin } from "./components/RequireAdmin";
import { TenantsTable } from "./components/tenants-table";
import { apiErrorMessage } from "./lib/api-errors";
import { navItems } from "./lib/nav";

const FILTERS = [
  { value: "all", label: "Todos" },
  { value: "needs_help", label: "Necesitan ayuda" },
  { value: "trial", label: "En prueba" },
] as const;

function filterFrom(value: string | null): BusinessFilter {
  return FILTERS.some((item) => item.value === value) ? (value as BusinessFilter) : "all";
}

/** S8 Negocios: KPIs, search, filters and every business. */
export function App() {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const filter = filterFrom(params.get("filtro"));
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(search);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: ["businesses", filter, debounced, page],
    queryFn: () => fetchBusinesses(filter, debounced, page),
    placeholderData: keepPreviousData,
  });
  const data = query.data;

  function choose(next: BusinessFilter) {
    setPage(1);
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next === "all") {
          updated.delete("filtro");
        } else {
          updated.set("filtro", next);
        }
        return updated;
      },
      { replace: true },
    );
  }

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Negocios"
        description="Clientes dados de alta en la plataforma."
        navItems={navItems(location.pathname)}
        action={<Button onClick={() => setCreating(true)}>Dar de alta un negocio</Button>}
      >
        <div className="flex flex-col gap-6">
          {data ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="Activos" value={data.kpis.active} />
              <KpiCard label="En prueba" value={data.kpis.trial} />
              <KpiCard label="Onboarding sin terminar" value={data.kpis.onboarding_unfinished} />
              <KpiCard label="WhatsApp con problemas" value={data.kpis.whatsapp_problems} />
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <SegmentedControl
              ariaLabel="Filtrar negocios"
              options={FILTERS}
              value={filter}
              onChange={choose}
            />
            <Input
              aria-label="Buscar por nombre o email"
              placeholder="Buscar por nombre o email"
              className="max-w-xs"
              value={search}
              onChange={(event) => {
                setPage(1);
                setSearch(event.target.value);
              }}
            />
          </div>

          {query.isPending ? (
            <p className="text-sm text-muted-foreground">Cargando negocios...</p>
          ) : null}

          {query.isError ? (
            <Card className="max-w-xl">
              <CardHeader>
                <CardTitle>No pudimos cargar los negocios</CardTitle>
                <CardDescription>
                  {apiErrorMessage(
                    query.error,
                    "Revisá que la API esté funcionando y volvé a intentarlo.",
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button onClick={() => void query.refetch()}>Reintentar</Button>
              </CardContent>
            </Card>
          ) : null}

          {data && data.total === 0 ? (
            <p className="text-sm text-muted-foreground">
              {filter === "needs_help"
                ? "Ningún negocio necesita ayuda ahora."
                : debounced
                  ? "No hay negocios que coincidan con la búsqueda."
                  : "Todavía no hay negocios."}
            </p>
          ) : null}

          {data && data.total > 0 ? (
            <Card>
              <CardContent>
                <TenantsTable businesses={data.items} />
                <Pagination
                  className="mt-4 border-t pt-4"
                  page={data.page}
                  pageSize={data.page_size}
                  total={data.total}
                  onPageChange={setPage}
                />
              </CardContent>
            </Card>
          ) : null}
        </div>
        <CreateBusinessDialog open={creating} onClose={() => setCreating(false)} />
      </PanelLayout>
    </RequireAdmin>
  );
}
