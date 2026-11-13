import type { ScheduleBlock, TenantSettings } from "@followup/api-client-cuentas-claras";
import {
  canEditSetup,
  NotificationEmailsField,
  parseEmails,
  TeamHoursField,
  trialDaysLeft,
} from "@followup/app-shell";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchMe } from "../api/me";
import { fetchPaymentSettings, saveTransferDetails } from "../api/payments";
import { WhatsAppSection } from "../components/WhatsAppSection";
import { fetchTenantSettings, saveTenantSettings } from "../api/tenant-settings";
import { apiErrorMessage } from "../lib/api-errors";
import { useAuth } from "../lib/auth";
import { businessTypes } from "../lib/product";

export function ConfiguracionPage() {
  const settingsQuery = useQuery({
    queryKey: ["tenant-settings"],
    queryFn: fetchTenantSettings,
  });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const { signOut } = useAuth();

  if (!settingsQuery.data || !meQuery.data) {
    return null;
  }
  const { profile, tenant } = meQuery.data;
  const days = trialDaysLeft(tenant.trial_ends_at);

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <SettingsForm
        key={JSON.stringify(settingsQuery.data)}
        settings={settingsQuery.data}
        readOnly={!canEditSetup(profile.role)}
      />
      <Card id="whatsapp">
        <CardHeader>
          <CardTitle>WhatsApp</CardTitle>
          <CardDescription>
            Los recordatorios salen desde tu número, con el nombre de tu negocio.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <WhatsAppSection />
        </CardContent>
      </Card>
      <TransferCard readOnly={!canEditSetup(profile.role)} />
      <Card>
        <CardHeader>
          <CardTitle>Cuenta</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p>
            <span className="text-muted-foreground">Email: </span>
            {profile.email}
          </p>
          <p>
            <span className="text-muted-foreground">Plan: </span>
            Prueba · {days} {days === 1 ? "día" : "días"}
          </p>
          <Button variant="outline" className="self-start" onClick={() => void signOut()}>
            Cerrar sesión
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function SettingsForm({
  settings,
  readOnly,
}: {
  settings: TenantSettings;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(settings.business_name);
  const [type, setType] = useState<string>(settings.business_type);
  const [hours, setHours] = useState<ScheduleBlock[]>(settings.business_hours);
  const [emails, setEmails] = useState(settings.notification_emails.join(", "));
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: saveTenantSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
  });

  function submit() {
    if (!name.trim()) {
      setLocalError("Ingresá el nombre de tu negocio.");
      return;
    }
    const notificationEmails = parseEmails(emails);
    if (notificationEmails.length === 0) {
      setLocalError("Ingresá al menos un email para los avisos.");
      return;
    }
    setLocalError(null);
    mutation.mutate({
      business_name: name.trim(),
      business_type: type,
      business_hours: hours,
      notification_emails: notificationEmails,
    });
  }

  const error =
    localError ??
    (mutation.isError
      ? apiErrorMessage(mutation.error, "No pudimos guardar los cambios. Probá de nuevo.")
      : null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuración</CardTitle>
        <CardDescription>
          Los recordatorios van a salir dentro del horario de tu equipo. Los avisos te llegan
          por email.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (!readOnly) {
              submit();
            }
          }}
        >
          <FormField label="Nombre del negocio" htmlFor="settings-name">
            <Input
              id="settings-name"
              value={name}
              disabled={readOnly}
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <FormField label="Tipo de negocio" htmlFor="settings-type">
            <select
              id="settings-type"
              value={type}
              disabled={readOnly}
              onChange={(event) => setType(event.target.value)}
              className="h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            >
              {businessTypes.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>
          <TeamHoursField value={hours} onChange={setHours} disabled={readOnly} />
          <NotificationEmailsField
            label="Emails para los avisos"
            value={emails}
            onChange={setEmails}
            disabled={readOnly}
          />
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          {mutation.isSuccess && !error ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Cambios guardados.
            </p>
          ) : null}
          {readOnly ? (
            <p className="text-sm text-muted-foreground">
              Solo el dueño o un encargado pueden cambiar estos datos.
            </p>
          ) : (
            <Button type="submit" className="self-start" disabled={mutation.isPending}>
              {mutation.isPending ? "Guardando..." : "Guardar cambios"}
            </Button>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

/** "Datos para transferencia": what a reminder's payment link shows until Mercado Pago. */
function TransferCard({ readOnly }: { readOnly: boolean }) {
  const query = useQuery({ queryKey: ["payment-settings"], queryFn: fetchPaymentSettings });
  return (
    <Card id="transferencia">
      <CardHeader>
        <CardTitle>Datos para transferencia</CardTitle>
        <CardDescription>
          Se muestran en el link de pago de cada recordatorio. Dejalos vacíos para no mostrarlos.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.data ? (
          <TransferForm
            key={JSON.stringify(query.data.transfer)}
            transfer={query.data.transfer}
            readOnly={readOnly}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

function TransferForm({
  transfer,
  readOnly,
}: {
  transfer: { cbu_or_alias: string; holder: string; bank: string | null } | null;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [cbu, setCbu] = useState(transfer?.cbu_or_alias ?? "");
  const [holder, setHolder] = useState(transfer?.holder ?? "");
  const [bank, setBank] = useState(transfer?.bank ?? "");
  const mutation = useMutation({
    mutationFn: () =>
      saveTransferDetails({ cbu_or_alias: cbu.trim(), holder: holder.trim(), bank: bank.trim() || null }),
    onSuccess: (result) => queryClient.setQueryData(["payment-settings"], result),
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!readOnly) {
          mutation.mutate();
        }
      }}
    >
      <FormField label="CBU, CVU o alias" htmlFor="transfer-cbu">
        <Input
          id="transfer-cbu"
          value={cbu}
          disabled={readOnly}
          placeholder="ascensores.delta"
          onChange={(event) => setCbu(event.target.value)}
        />
      </FormField>
      <FormField label="Titular" htmlFor="transfer-holder">
        <Input
          id="transfer-holder"
          value={holder}
          disabled={readOnly}
          onChange={(event) => setHolder(event.target.value)}
        />
      </FormField>
      <FormField label="Banco (opcional)" htmlFor="transfer-bank">
        <Input
          id="transfer-bank"
          value={bank}
          disabled={readOnly}
          onChange={(event) => setBank(event.target.value)}
        />
      </FormField>
      {mutation.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(mutation.error, "No pudimos guardar los datos.")}
        </p>
      ) : null}
      {mutation.isSuccess ? (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {mutation.data.transfer ? "Datos guardados." : "Quitamos los datos para transferencia."}
        </p>
      ) : null}
      {readOnly ? null : (
        <Button type="submit" className="self-start" disabled={mutation.isPending}>
          {mutation.isPending ? "Guardando..." : "Guardar datos"}
        </Button>
      )}
    </form>
  );
}
