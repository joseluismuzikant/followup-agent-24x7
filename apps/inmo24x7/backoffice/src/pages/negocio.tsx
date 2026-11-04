import type { BusinessDetail } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  FormField,
  Input,
  PanelLayout,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import {
  fetchBusiness,
  fetchErrors,
  fetchSystemHealth,
  fetchTenantUsage,
  reactivateBusiness,
  retrySignup,
  sendReconnectLink,
  suspendBusiness,
} from "../api/backoffice";
import { RequireAdmin } from "../components/RequireAdmin";
import { IssueList, errorsUnavailableText } from "../components/monitoring/IssueList";
import { WhatsAppConnectionPanel } from "../components/WhatsAppConnection";
import { apiErrorMessage } from "../lib/api-errors";
import {
  activityText,
  actorText,
  badgeLabels,
  badgeTones,
  formatDate,
  currentMonth,
  formatCount,
  formatCost,
  formatDateTime,
  onboardingLabels,
  planLabel,
  roleLabels,
} from "../lib/labels";
import { grafanaExploreUrl, tenantLogsQuery } from "../lib/monitoring";
import { navItems } from "../lib/nav";

const verificationLabels: Record<string, string> = {
  verified: "Verificada",
  pending: "En revisión",
  failed: "Rechazada",
  unknown: "Meta no la informa",
};

const number = new Intl.NumberFormat("es-AR");

/** S9 Detalle del negocio. */
export function NegocioPage() {
  const location = useLocation();
  const { tenantId = "" } = useParams();
  const queryKey = ["business", tenantId];
  const query = useQuery({ queryKey, queryFn: () => fetchBusiness(tenantId) });
  const business = query.data;

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title={business?.name ?? "Negocio"}
        description="Detalle del negocio."
        navItems={navItems(location.pathname)}
      >
        {query.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(query.error, "No pudimos cargar el negocio.")}
          </p>
        ) : null}
        {business ? <Detail business={business} queryKey={queryKey} /> : null}
      </PanelLayout>
    </RequireAdmin>
  );
}

type DetailProps = { business: BusinessDetail; queryKey: string[] };

function Detail({ business, queryKey }: DetailProps) {
  const [suspending, setSuspending] = useState(false);
  const queryClient = useQueryClient();
  const reactivate = useMutation({
    mutationFn: () => reactivateBusiness(business.id),
    onSuccess: (updated) => queryClient.setQueryData(queryKey, updated),
  });
  const suspended = business.status === "suspended";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{planLabel(business.plan)}</Badge>
            {suspended ? <Badge tone="danger">Suspendido</Badge> : null}
            <span className="text-muted-foreground">Alta {formatDate(business.created_at)}</span>
          </div>
          <span>
            Dueño: {business.owner_email ?? "sin dueño"}
            {business.owner_pending ? " (todavía no entró)" : ""}
          </span>
          {suspended && business.suspended_reason ? (
            <span className="text-destructive">Motivo: {business.suspended_reason}</span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to={`/simulador?negocio=${business.id}`}>Probar su agente</Link>
          </Button>
          {suspended ? (
            <Button disabled={reactivate.isPending} onClick={() => reactivate.mutate()}>
              Reactivar
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setSuspending(true)}>
              Suspender
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex flex-col gap-6">
          <WhatsAppCard business={business} queryKey={queryKey} />
          <BusinessErrorsCard tenantId={business.id} />
          <ActivityCard business={business} />
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Onboarding · {business.onboarding_done} de {business.onboarding_total}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-2 text-sm">
                {business.onboarding.map((item) => (
                  <li key={item.key} className="flex items-center gap-2">
                    <span aria-hidden="true">{item.done ? "✓" : "•"}</span>
                    <span className={item.done ? "" : "text-muted-foreground"}>
                      {onboardingLabels[item.key]}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <UsageCard tenantId={business.id} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Plan</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <p>
                Conversaciones este mes:{" "}
                <strong>
                  {number.format(business.usage.conversations_this_month)} de{" "}
                  {number.format(business.usage.allowance)}
                </strong>
              </p>
              <p>Usuarios: {business.usage.users}</p>
              <Button variant="outline" size="sm" className="self-start" disabled>
                Cambiar plan · Próximamente
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Usuarios</CardTitle>
            </CardHeader>
            <CardContent>
              {business.users.length === 0 ? (
                <p className="text-sm text-muted-foreground">Todavía nadie entró.</p>
              ) : (
                <ul className="flex flex-col gap-2 text-sm">
                  {business.users.map((user) => (
                    <li key={user.id} className="flex justify-between gap-3">
                      <span className="truncate">
                        {user.name}
                        {user.name !== user.email ? (
                          <span className="block text-xs text-muted-foreground">{user.email}</span>
                        ) : null}
                      </span>
                      <span className="text-muted-foreground">{roleLabels[user.role] ?? user.role}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <SuspendDialog
        business={business}
        queryKey={queryKey}
        open={suspending}
        onClose={() => setSuspending(false)}
      />
    </div>
  );
}

function WhatsAppCard({ business, queryKey }: DetailProps) {
  const queryClient = useQueryClient();
  const [showTechnical, setShowTechnical] = useState(false);
  const [manual, setManual] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const connection = business.whatsapp_connection;
  const error = connection.admin_error;
  const refresh = () => queryClient.invalidateQueries({ queryKey });
  const link = useMutation({
    mutationFn: () => sendReconnectLink(business.id),
    onSuccess: (recipients) =>
      setNotice(
        recipients === 1
          ? "Le mandamos el link al dueño."
          : `Le mandamos el link a los ${recipients} dueños.`,
      ),
  });
  const retry = useMutation({
    mutationFn: () => retrySignup(business.id),
    onSuccess: async () => {
      setNotice("La configuración terminó bien.");
      await refresh();
    },
    onError: () => void refresh(),
  });
  const failing = connection.status === "error";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">WhatsApp</CardTitle>
        <Badge tone={badgeTones[business.whatsapp]}>{badgeLabels[business.whatsapp]}</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {error ? (
          <div role="alert" className="flex flex-col gap-1 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-rose-900">
            <p className="font-medium">{error.title}</p>
            <p>{error.admin_detail}</p>
            {failing && connection.failing_since ? (
              <p>Los mensajes fallan desde {formatDateTime(connection.failing_since)}.</p>
            ) : null}
            <button
              type="button"
              className="self-start text-xs underline"
              onClick={() => setShowTechnical((value) => !value)}
            >
              Código de Meta: {error.meta_code || error.code} · ver detalle técnico
            </button>
            {showTechnical ? (
              <p className="text-xs">
                Código interno: {error.code}. Al cliente le mostramos: {error.message}{" "}
                {error.action}
              </p>
            ) : null}
          </div>
        ) : null}
        {connection.signup_step && connection.signup_error ? (
          <p className="text-amber-900">
            La conexión con Meta quedó a mitad de camino ({connection.signup_step}):{" "}
            {connection.signup_error.title}.
          </p>
        ) : null}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">Número</dt>
          <dd>
            {[connection.display_phone_number, connection.verified_name]
              .filter(Boolean)
              .join(" · ") || "—"}
          </dd>
          <dt className="text-muted-foreground">WABA</dt>
          <dd>{connection.waba_masked ?? "—"}</dd>
          <dt className="text-muted-foreground">Verificación de empresa</dt>
          <dd>
            {connection.business_verification
              ? verificationLabels[connection.business_verification]
              : "—"}
          </dd>
          <dt className="text-muted-foreground">Último mensaje recibido</dt>
          <dd>{connection.last_inbound_at ? formatDateTime(connection.last_inbound_at) : "—"}</dd>
        </dl>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={link.isPending || business.owner_pending}
            onClick={() => link.mutate()}
          >
            Enviarle link para reconectar
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={retry.isPending}
            onClick={() => retry.mutate()}
          >
            Reintentar configuración
          </Button>
          <Button variant="outline" size="sm" onClick={() => setManual((value) => !value)}>
            {manual ? "Ocultar conexión manual" : "Conexión manual y mensaje de prueba"}
          </Button>
        </div>
        {notice ? <p className="text-emerald-800">{notice}</p> : null}
        {link.isError || retry.isError ? (
          <p className="text-destructive" role="alert">
            {apiErrorMessage(link.error ?? retry.error, "No pudimos hacerlo. Probá de nuevo.")}
          </p>
        ) : null}
        {manual ? <WhatsAppConnectionPanel tenantId={business.id} onSaved={refresh} /> : null}
      </CardContent>
    </Card>
  );
}

/** Sentry issues tagged with this business in the last 7 days, and its logs in Grafana. */
function BusinessErrorsCard({ tenantId }: { tenantId: string }) {
  const errors = useQuery({
    queryKey: ["errors", "all", "7d", tenantId],
    queryFn: () => fetchErrors({ period: "7d", tenantId, limit: 25 }),
  });
  const system = useQuery({ queryKey: ["system"], queryFn: fetchSystemHealth });
  const logs = grafanaExploreUrl(system.data?.links, tenantLogsQuery(tenantId));
  const list = errors.data;
  const unavailable = list ? errorsUnavailableText(list) : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <CardTitle className="text-base">
            Errores de este negocio (7 días)
            {list && !unavailable ? ` · ${list.issues.length}` : ""}
          </CardTitle>
          <CardDescription>Los últimos cinco, de Sentry.</CardDescription>
        </div>
        {logs ? (
          <Button asChild variant="outline" size="sm">
            <a href={logs} target="_blank" rel="noreferrer">
              Ver logs
            </a>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {errors.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(errors.error, "No pudimos leer los errores.")}
          </p>
        ) : null}
        {unavailable ? <p className="text-sm text-muted-foreground">{unavailable}</p> : null}
        {list && !unavailable ? (
          <IssueList issues={list.issues.slice(0, 5)} empty="Sin errores en los últimos 7 días." />
        ) : null}
      </CardContent>
    </Card>
  );
}

/** This month's LLM cost (UTC) with a link to its Consumo detail. */
function UsageCard({ tenantId }: { tenantId: string }) {
  const month = currentMonth();
  const query = useQuery({
    queryKey: ["usage", month, tenantId],
    queryFn: () => fetchTenantUsage(tenantId, month),
  });
  const figures = query.data?.business.figures;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Consumo este mes</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        {query.isError ? (
          <p className="text-destructive" role="alert">
            {apiErrorMessage(query.error, "No pudimos leer el consumo.")}
          </p>
        ) : null}
        {figures ? (
          <>
            <p>
              Costo del LLM: <strong>{formatCost(figures.cost_usd, figures)}</strong>
              {figures.unpriced_calls ? (
                <Badge tone="warning" className="ml-2">
                  sin precio
                </Badge>
              ) : null}
            </p>
            <p>Conversaciones: {formatCount(figures.conversations)}</p>
            <p>Por conversación: {formatCost(figures.cost_per_conversation_usd, figures)}</p>
          </>
        ) : null}
        <Button asChild variant="outline" size="sm" className="self-start">
          <Link to={`/consumo?negocio=${tenantId}&mes=${month}`}>Ver el detalle</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function ActivityCard({ business }: { business: BusinessDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Actividad</CardTitle>
        <CardDescription>Los últimos 20 eventos.</CardDescription>
      </CardHeader>
      <CardContent>
        {business.activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin actividad todavía.</p>
        ) : (
          <ol className="flex flex-col gap-3 text-sm">
            {business.activity.map((event, index) => (
              <li key={`${event.at}-${index}`} className="flex flex-col">
                <span>{activityText(event)}</span>
                <span className="text-xs text-muted-foreground">
                  {actorText(event)} · {formatDateTime(event.at)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function SuspendDialog({
  business,
  queryKey,
  open,
  onClose,
}: DetailProps & { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const suspend = useMutation({
    mutationFn: () => suspendBusiness(business.id, reason.trim()),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKey, updated);
      onClose();
    },
  });

  return (
    <Dialog open={open} title={`Suspender ${business.name}`} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          suspend.mutate();
        }}
      >
        <p className="text-sm text-muted-foreground">
          No se borra nada: el panel queda bloqueado, el agente deja de responder y no salen
          emails. Los mensajes que lleguen se guardan.
        </p>
        <FormField label="Motivo" htmlFor="suspend-reason" hint="Solo lo ven los administradores.">
          <Input
            id="suspend-reason"
            value={reason}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
          />
        </FormField>
        {suspend.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(suspend.error, "No pudimos suspenderlo.")}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!reason.trim() || suspend.isPending}>
            Suspender
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
