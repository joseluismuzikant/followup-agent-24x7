import type { ScheduleBlock, TenantSettings } from "@followup/api-client-inmo24x7";
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
import { fetchTenantSettings, saveTenantSettings } from "../api/tenant-settings";
import { NotificationEmailsField } from "../components/NotificationEmailsField";
import { TeamHoursField } from "../components/TeamHoursField";
import { apiErrorMessage } from "../lib/api-errors";
import { useAuth } from "../lib/auth";
import { businessTypes, canEditSetup, parseEmails, trialDaysLeft } from "../lib/setup";

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
  const [type, setType] = useState(settings.business_type);
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
          El horario y los avisos son los mismos que configuraste para tu agente.
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
            label="Avisos de nuevos leads"
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
