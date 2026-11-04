import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  KpiCard,
  PanelLayout,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router";

import { fetchSystemHealth } from "../api/backoffice";
import { RequireAdmin } from "../components/RequireAdmin";
import { apiErrorMessage } from "../lib/api-errors";
import { formatAge } from "../lib/labels";
import { navItems } from "../lib/nav";

const statusLabels: Record<string, string> = {
  queued: "En cola",
  running: "Corriendo",
  failed: "Reintentando",
  dead: "Muertos (24 h)",
};

/** Salud del sistema: jobs, webhooks and failed sends. */
export function SistemaPage() {
  const location = useLocation();
  const query = useQuery({
    queryKey: ["system"],
    queryFn: fetchSystemHealth,
    refetchInterval: 30_000,
  });
  const system = query.data;

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Salud del sistema"
        description="Jobs, webhooks de Meta y envíos de las últimas horas."
        navItems={navItems(location.pathname)}
        action={
          <Button variant="outline" onClick={() => void query.refetch()} disabled={query.isFetching}>
            Actualizar
          </Button>
        }
      >
        {query.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(query.error, "No pudimos leer el estado del sistema.")}
          </p>
        ) : null}
        {system ? (
          <div className="flex flex-col gap-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="Webhooks (última hora)" value={system.webhooks_last_hour} />
              <KpiCard
                label="Firmas rechazadas (24 h)"
                value={system.signature_rejections_last_24h}
              />
              <KpiCard label="Jobs muertos (24 h)" value={system.dead_last_24h} />
              <KpiCard
                label="Job en cola más viejo"
                value={formatAge(system.oldest_queued_seconds)}
              />
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Jobs</CardTitle>
                </CardHeader>
                <CardContent>
                  {system.jobs.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No hay jobs pendientes.</p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Tipo</TableHead>
                          <TableHead>Estado</TableHead>
                          <TableHead className="text-right">Cantidad</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {system.jobs.map((job) => (
                          <TableRow key={`${job.kind}-${job.status}`}>
                            <TableCell className="font-mono text-xs">{job.kind}</TableCell>
                            <TableCell>{statusLabels[job.status] ?? job.status}</TableCell>
                            <TableCell className="text-right">{job.count}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Envíos fallidos (24 h)</CardTitle>
                </CardHeader>
                <CardContent>
                  {system.failed_sends_last_24h.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Ningún envío falló.</p>
                  ) : (
                    <ul className="flex flex-col gap-1 text-sm">
                      {system.failed_sends_last_24h.map((item) => (
                        <li key={item.code} className="flex justify-between">
                          <span>Código de Meta {item.code}</span>
                          <span>{item.count}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge tone={system.database === "ok" ? "success" : "danger"}>
                Base de datos {system.database === "ok" ? "OK" : "no disponible"}
              </Badge>
              <span>
                Versión {system.version} · commit {system.commit}
              </span>
            </div>
          </div>
        ) : null}
      </PanelLayout>
    </RequireAdmin>
  );
}
