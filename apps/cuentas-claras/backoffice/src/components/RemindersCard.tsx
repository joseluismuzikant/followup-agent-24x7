import type { AdminReminders } from "@followup/api-client-cuentas-claras";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchAdminReminders, planReminders, syncTemplates } from "../api/reminders";
import { apiErrorMessage } from "../lib/api-errors";
import { formatDateTime } from "../lib/labels";

const kindLabels: Record<string, string> = {
  before: "Antes del vencimiento",
  due: "El día del vencimiento",
  after: "Después del vencimiento",
  several: "Varias facturas",
};

function tone(status: AdminReminders["templates"][number]["status"]) {
  if (status === "approved") {
    return "success" as const;
  }
  if (status === "pending" || status === "not_submitted") {
    return "warning" as const;
  }
  return "danger" as const;
}

const pausedLabels: Record<string, string> = {
  none: "no tiene WhatsApp conectado",
  error: "la conexión de WhatsApp tiene un error",
  tenant_suspended: "el negocio está suspendido",
};

/** C5 (Day 9): the business's templates and their Meta status, the last reminders that did
 * not go out, and "Planificar ahora". */
export function RemindersCard({ tenantId }: { tenantId: string }) {
  const queryClient = useQueryClient();
  const queryKey = ["admin-reminders", tenantId];
  const query = useQuery({ queryKey, queryFn: () => fetchAdminReminders(tenantId) });
  const plan = useMutation({
    mutationFn: () => planReminders(tenantId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });
  const sync = useMutation({ mutationFn: () => syncTemplates(tenantId) });

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-base">Recordatorios</CardTitle>
          <CardDescription>
            {query.data
              ? `${query.data.month_count} enviados este mes${query.data.configured ? "" : " · política sin guardar (la de fábrica)"}`
              : "Plantillas y envíos."}
          </CardDescription>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
            Actualizar estados
          </Button>
          <Button size="sm" disabled={plan.isPending} onClick={() => plan.mutate()}>
            {plan.isPending ? "Planificando..." : "Planificar ahora"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {plan.data ? (
          <p role="status" className="text-emerald-700">
            {plan.data.paused
              ? `No salió nada: ${pausedLabels[plan.data.paused] ?? plan.data.paused}.`
              : `Listo: ${plan.data.sends} envíos programados, ${plan.data.escalated} escalados al dueño.`}
          </p>
        ) : null}
        {sync.isSuccess ? <p role="status">Pedimos los estados a Meta: en un momento se actualizan.</p> : null}
        {plan.isError || query.isError ? (
          <p role="alert" className="text-destructive">
            {apiErrorMessage(plan.error ?? query.error, "No pudimos cargar los recordatorios.")}
          </p>
        ) : null}
        {query.data ? (
          <>
            <section aria-label="Plantillas" className="flex flex-col gap-2">
              <h3 className="font-semibold">Plantillas</h3>
              {query.data.templates.length === 0 ? (
                <p className="text-muted-foreground">Se crean al conectar WhatsApp.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {query.data.templates.map((template) => (
                    <li key={template.name} className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        <span className="block">{kindLabels[template.kind] ?? template.kind}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {template.name}
                          {template.last_synced_at ? ` · ${formatDateTime(template.last_synced_at)}` : ""}
                        </span>
                      </span>
                      <Badge tone={tone(template.status)}>{template.status_label}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-label="Últimos errores" className="flex flex-col gap-2">
              <h3 className="font-semibold">Últimos que no salieron</h3>
              {query.data.errors.length === 0 ? (
                <p className="text-muted-foreground">Ninguno.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {query.data.errors.map((event, index) => (
                    <li key={`${event.at}-${index}`} className="flex justify-between gap-3">
                      <span>
                        {event.outcome === "failed" ? "Meta lo rechazó" : "No salió"}:{" "}
                        {event.reason_label ?? (event.reason ? `código ${event.reason}` : "sin motivo")}
                      </span>
                      <span className="shrink-0 text-muted-foreground">{formatDateTime(event.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
