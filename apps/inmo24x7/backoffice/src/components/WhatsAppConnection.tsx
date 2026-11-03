import type { WhatsAppConnection } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  FormField,
  Input,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  fetchConnection,
  runConnectionAction,
  saveConnection,
  sendTestMessage,
} from "../api/whatsapp";
import type { ConnectionAction } from "../api/whatsapp";
import { apiErrorMessage } from "../lib/api-errors";

const statusLabels = {
  connected: { label: "Conectado", tone: "success" },
  disconnected: { label: "Desconectado", tone: "neutral" },
  error: { label: "Error", tone: "danger" },
  not_connected: { label: "Sin conectar", tone: "neutral" },
} as const;

const dateTime = new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short" });

export function ConnectionStatusCard({ connection }: { connection: WhatsAppConnection }) {
  const status = statusLabels[connection.status];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">Estado</CardTitle>
        <Badge tone={status.tone}>{status.label}</Badge>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Número</dt>
          <dd>{connection.display_phone_number ?? "—"}</dd>
          <dt className="text-muted-foreground">Nombre verificado</dt>
          <dd>{connection.verified_name ?? "—"}</dd>
          <dt className="text-muted-foreground">Envío</dt>
          <dd>{connection.sender === "log" ? "Solo log (desarrollo)" : "Cloud API"}</dd>
          <dt className="text-muted-foreground">Último error</dt>
          <dd>{connection.last_error_code ? `Código ${connection.last_error_code}` : "—"}</dd>
          <dt className="text-muted-foreground">Último mensaje recibido</dt>
          <dd>
            {connection.last_inbound_at
              ? dateTime.format(new Date(connection.last_inbound_at))
              : "Todavía ninguno"}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

const actionLabels: Record<ConnectionAction, string> = {
  test: "Probar conexión",
  subscribe: "Suscribir la app",
  disconnect: "Desconectar",
};

const actionDone: Record<ConnectionAction, string> = {
  test: "La conexión funciona: actualizamos el número y el nombre.",
  subscribe: "La app quedó suscripta a los mensajes de esta cuenta.",
  disconnect: "El número quedó desconectado: los mensajes que lleguen se ignoran.",
};

/** Manual connection of a business's number (Day 7 adds Embedded Signup). */
export function WhatsAppConnectionPanel({ tenantId }: { tenantId: string }) {
  const queryClient = useQueryClient();
  const queryKey = ["whatsapp-connection", tenantId];
  const connectionQuery = useQuery({ queryKey, queryFn: () => fetchConnection(tenantId) });
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);

  function done(text: string, connection?: WhatsAppConnection) {
    if (connection) {
      queryClient.setQueryData(queryKey, connection);
    }
    setNotice({ text, error: false });
  }
  function failed(error: unknown) {
    setNotice({ text: apiErrorMessage(error, "No pudimos hacerlo. Probá de nuevo."), error: true });
    void queryClient.invalidateQueries({ queryKey });
  }

  const save = useMutation({
    mutationFn: (form: ConnectionForm) =>
      saveConnection(tenantId, {
        phone_number_id: form.phoneNumberId,
        waba_id: form.wabaId,
        display_phone_number: form.displayPhoneNumber || null,
        access_token: form.accessToken || null,
        sender: form.sender,
      }),
    onSuccess: (connection) => done("Guardamos la conexión.", connection),
    onError: failed,
  });
  const action = useMutation({
    mutationFn: (name: ConnectionAction) => runConnectionAction(tenantId, name),
    onSuccess: (connection, name) => done(actionDone[name], connection),
    onError: failed,
  });
  const testMessage = useMutation({
    mutationFn: (to: string) => sendTestMessage(tenantId, to),
    onSuccess: () => done("Enviamos el mensaje de prueba."),
    onError: failed,
  });

  if (connectionQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Cargando...</p>;
  }
  if (connectionQuery.isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(connectionQuery.error, "No pudimos cargar la conexión.")}
      </p>
    );
  }
  const connection = connectionQuery.data;
  const exists = connection.status !== "not_connected";
  const busy = save.isPending || action.isPending || testMessage.isPending;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Datos de Meta</CardTitle>
          </CardHeader>
          <CardContent>
            <ConnectionFormFields
              key={connection.updated_at ?? "new"}
              connection={connection}
              saving={save.isPending}
              onSubmit={(form) => save.mutate(form)}
            />
          </CardContent>
        </Card>
        {exists ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Acciones</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-wrap gap-2">
                {(["test", "subscribe"] as const).map((name) => (
                  <Button
                    key={name}
                    variant="outline"
                    disabled={busy}
                    onClick={() => action.mutate(name)}
                  >
                    {actionLabels[name]}
                  </Button>
                ))}
                <Button
                  variant="destructive"
                  disabled={busy || connection.status === "disconnected"}
                  onClick={() => action.mutate("disconnect")}
                >
                  {actionLabels.disconnect}
                </Button>
              </div>
              <TestMessageForm
                template={connection.template_name ?? "hello_world"}
                disabled={busy}
                onSend={(to) => testMessage.mutate(to)}
              />
            </CardContent>
          </Card>
        ) : null}
        {notice ? (
          <p
            className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-700"}
            role={notice.error ? "alert" : "status"}
          >
            {notice.text}
          </p>
        ) : null}
      </div>
      {exists ? <ConnectionStatusCard connection={connection} /> : null}
    </div>
  );
}

interface ConnectionForm {
  phoneNumberId: string;
  wabaId: string;
  displayPhoneNumber: string;
  accessToken: string;
  sender: "cloud" | "log";
}

function ConnectionFormFields({
  connection,
  saving,
  onSubmit,
}: {
  connection: WhatsAppConnection;
  saving: boolean;
  onSubmit: (form: ConnectionForm) => void;
}) {
  const ids = { phone: useId(), waba: useId(), display: useId(), token: useId(), sender: useId() };
  const [form, setForm] = useState<ConnectionForm>({
    phoneNumberId: connection.phone_number_id ?? "",
    wabaId: connection.waba_id ?? "",
    displayPhoneNumber: connection.display_phone_number ?? "",
    accessToken: "",
    sender: connection.sender ?? "cloud",
  });
  const [error, setError] = useState<string | null>(null);
  const update = (changes: Partial<ConnectionForm>) => setForm({ ...form, ...changes });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!form.phoneNumberId.trim() || !form.wabaId.trim()) {
          setError("Completá el phone_number_id y el WABA id.");
          return;
        }
        if (!connection.has_access_token && !form.accessToken.trim()) {
          setError("Pegá el token de acceso (de un usuario del sistema, no el temporal de 24 h).");
          return;
        }
        setError(null);
        onSubmit({ ...form, accessToken: form.accessToken.trim() });
      }}
    >
      <FormField label="Phone number ID" htmlFor={ids.phone}>
        <Input
          id={ids.phone}
          value={form.phoneNumberId}
          onChange={(event) => update({ phoneNumberId: event.target.value })}
        />
      </FormField>
      <FormField label="WABA ID" htmlFor={ids.waba}>
        <Input
          id={ids.waba}
          value={form.wabaId}
          onChange={(event) => update({ wabaId: event.target.value })}
        />
      </FormField>
      <FormField label="Número para mostrar" htmlFor={ids.display} hint="Se completa solo al probar la conexión.">
        <Input
          id={ids.display}
          value={form.displayPhoneNumber}
          placeholder="+54 9 11 5555-0100"
          onChange={(event) => update({ displayPhoneNumber: event.target.value })}
        />
      </FormField>
      <FormField
        label="Token de acceso"
        htmlFor={ids.token}
        hint={
          connection.has_access_token
            ? "Ya hay un token guardado. Dejalo vacío para conservarlo."
            : "Un token de usuario del sistema con whatsapp_business_messaging y whatsapp_business_management."
        }
      >
        <Input
          id={ids.token}
          type="password"
          autoComplete="off"
          value={form.accessToken}
          onChange={(event) => update({ accessToken: event.target.value })}
        />
      </FormField>
      <FormField label="Envío" htmlFor={ids.sender}>
        <select
          id={ids.sender}
          value={form.sender}
          onChange={(event) => update({ sender: event.target.value as ConnectionForm["sender"] })}
          className="h-10 rounded-md border bg-card px-3 text-sm"
        >
          <option value="cloud">Cloud API (real)</option>
          <option value="log">Solo log (desarrollo, no llega a Meta)</option>
        </select>
      </FormField>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" className="self-start" disabled={saving}>
        {saving ? "Guardando..." : "Guardar"}
      </Button>
    </form>
  );
}

function TestMessageForm({
  template,
  disabled,
  onSend,
}: {
  template: string;
  disabled: boolean;
  onSend: (to: string) => void;
}) {
  const inputId = useId();
  const [to, setTo] = useState("");
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (to.trim()) {
          onSend(to.trim());
        }
      }}
    >
      <FormField
        label="Enviar mensaje de prueba a"
        htmlFor={inputId}
        hint={`Manda la plantilla «${template}».`}
      >
        <Input
          id={inputId}
          value={to}
          placeholder="+54 9 11 5555-0188"
          onChange={(event) => setTo(event.target.value)}
        />
      </FormField>
      <Button type="submit" variant="outline" disabled={disabled || !to.trim()}>
        Enviar mensaje de prueba
      </Button>
    </form>
  );
}
