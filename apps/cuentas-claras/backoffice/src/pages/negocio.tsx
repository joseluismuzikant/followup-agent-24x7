import type { BusinessDetail } from "@followup/api-client-cuentas-claras";
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
import { OwnerInvitationCard } from "@followup/app-shell";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useParams } from "react-router";

import {
  fetchBusiness,
  reactivateBusiness,
  resendInvitation,
  resetTemporaryPassword,
  suspendBusiness,
} from "../api/backoffice";
import { RequireAdmin } from "../components/RequireAdmin";
import { apiErrorMessage } from "../lib/api-errors";
import {
  activityText,
  actorText,
  checklistLabels,
  formatDate,
  formatDateTime,
  formatPesos,
  navItems,
  planLabel,
  PRODUCT_NAME,
} from "../lib/labels";

/** Detalle del negocio: plan, owner, checklist, activity, Suspender / Reactivar. */
export function NegocioPage() {
  const location = useLocation();
  const { tenantId = "" } = useParams();
  const queryKey = ["business", tenantId];
  const query = useQuery({ queryKey, queryFn: () => fetchBusiness(tenantId) });
  const business = query.data;

  return (
    <RequireAdmin>
      <PanelLayout
        productName={PRODUCT_NAME}
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
      {reactivate.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(reactivate.error, "No pudimos reactivarlo.")}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex flex-col gap-6">
          {business.owner_pending ? (
            <OwnerInvitationCard
              ownerEmail={business.owner_email}
              resend={() => resendInvitation(business.id)}
              resetPassword={() => resetTemporaryPassword(business.id)}
            />
          ) : null}
          <ActivityCard business={business} />
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Configuración · {business.onboarding_done} de {business.onboarding_total}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-2 text-sm">
                {business.checklist.map((item) => (
                  <li key={item.key} className="flex items-center gap-2">
                    <span aria-hidden="true">{item.done ? "✓" : "•"}</span>
                    <span className={item.done ? "" : "text-muted-foreground"}>
                      {checklistLabels[item.key] ?? item.key}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cartera</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <p>
                Clientes: <strong>{business.clients}</strong>
              </p>
              <p>
                A cobrar: <strong>{formatPesos(business.open_amount)}</strong>
              </p>
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
          No se borra nada: el panel queda bloqueado hasta que lo reactives.
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
