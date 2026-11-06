import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Pagination,
  PanelLayout,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CreateBusinessDialog } from "@followup/app-shell";
import { Link, useLocation, useNavigate } from "react-router";

import { createBusiness, fetchBusinesses } from "./api/backoffice";
import { RequireAdmin } from "./components/RequireAdmin";
import { apiErrorMessage } from "./lib/api-errors";
import { formatDate, formatPesos, navItems, planLabel, PRODUCT_NAME } from "./lib/labels";

/** Negocios: every Cuentas Claras business, with search. */
export function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState(search);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: ["businesses", debounced, page],
    queryFn: () => fetchBusinesses(debounced, page),
    placeholderData: keepPreviousData,
  });
  const data = query.data;

  return (
    <RequireAdmin>
      <PanelLayout
        productName={PRODUCT_NAME}
        areaName="Backoffice"
        title="Negocios"
        description="Negocios dados de alta en Cuentas Claras."
        navItems={navItems(location.pathname)}
        action={<Button onClick={() => setCreating(true)}>Dar de alta un negocio</Button>}
      >
        <CreateBusinessDialog
          open={creating}
          onClose={() => setCreating(false)}
          businessType="mantenimiento"
          create={createBusiness}
          onCreated={(business) => void navigate(`/negocios/${business.id}`)}
        />
        <div className="flex flex-col gap-6">
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
              {debounced ? "No hay negocios que coincidan con la búsqueda." : "Todavía no hay negocios."}
            </p>
          ) : null}

          {data && data.total > 0 ? (
            <Card>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Negocio</TableHead>
                        <TableHead>Dueño</TableHead>
                        <TableHead>Plan</TableHead>
                        <TableHead>Onboarding</TableHead>
                        <TableHead className="text-right">Clientes</TableHead>
                        <TableHead className="text-right">A cobrar</TableHead>
                        <TableHead>Alta</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((business) => (
                        <TableRow key={business.id}>
                          <TableCell>
                            <Link
                              to={`/negocios/${business.id}`}
                              className="font-medium text-primary underline-offset-4 hover:underline"
                            >
                              {business.name}
                            </Link>
                            {business.status === "suspended" ? (
                              <span className="block text-xs text-destructive">Suspendido</span>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            {business.owner_email ?? "sin dueño"}
                            {business.owner_pending ? (
                              <span className="block text-xs text-muted-foreground">todavía no entró</span>
                            ) : null}
                          </TableCell>
                          <TableCell className="whitespace-nowrap">{planLabel(business.plan)}</TableCell>
                          <TableCell className="whitespace-nowrap tabular-nums">
                            {business.onboarding_done} de {business.onboarding_total}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{business.clients}</TableCell>
                          <TableCell className="whitespace-nowrap text-right tabular-nums">
                            {formatPesos(business.open_amount)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap">{formatDate(business.created_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
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
      </PanelLayout>
    </RequireAdmin>
  );
}
