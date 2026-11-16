import type { ReminderSettings, ReminderTemplate } from "@followup/api-client-cuentas-claras";
import { canEditSetup, ConnectionErrorBanner } from "@followup/app-shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";

import { fetchMe } from "../api/me";
import { fetchReminders, saveTemplateText } from "../api/reminders";
import { ReminderPolicyEditor, TemplateStatusBadge } from "../components/ReminderPolicyEditor";
import { useWhatsAppStatus } from "../components/WhatsAppSection";
import { apiErrorMessage } from "../lib/api-errors";

const FIELD_LABELS: Record<string, string> = {
  cliente: "nombre del cliente",
  negocio: "tu negocio",
  factura: "número de factura (o las facturas)",
  monto: "monto (o el total)",
  vencimiento: "vencimiento (dd/mm)",
};

/** C4 "Recordatorios y cobros". */
export function RecordatoriosPage() {
  const remindersQuery = useQuery({ queryKey: ["reminders"], queryFn: fetchReminders });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const whatsapp = useWhatsAppStatus();

  if (remindersQuery.isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(remindersQuery.error, "No pudimos cargar los recordatorios.")}
      </p>
    );
  }
  if (!remindersQuery.data || !meQuery.data) {
    return null;
  }
  const settings = remindersQuery.data;
  const canEdit = canEditSetup(meQuery.data.profile.role);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <ConnectionErrorBanner status={whatsapp.data} />
      <Card>
        <CardHeader>
          <CardTitle>Secuencia de recordatorios</CardTitle>
          <CardDescription>
            Cuándo le escribimos a cada cliente por WhatsApp, y cuándo te avisamos para que sigas
            vos.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ReminderPolicyEditor
            key={JSON.stringify(settings.steps) + settings.window.preset}
            settings={settings}
            canEdit={canEdit}
          />
        </CardContent>
      </Card>

      <TemplatesCard settings={settings} canEdit={canEdit} />

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">WhatsApp</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {settings.whatsapp.status === "not_connected" ? (
              <>
                <p className="text-muted-foreground">
                  Todavía no conectaste un número: los recordatorios no salen.
                </p>
                <Link
                  to="/configuracion#whatsapp"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  Conectar WhatsApp
                </Link>
              </>
            ) : (
              <p>
                <span className="text-muted-foreground">Número: </span>
                {settings.whatsapp.display_phone_number ?? "—"}
              </p>
            )}
            <p>
              <span className="text-muted-foreground">Este mes: </span>
              {settings.month_count === 1
                ? "1 mensaje de recordatorio"
                : `${settings.month_count} mensajes de recordatorio`}
            </p>
            <p className="text-xs text-muted-foreground">
              Meta cobra cada mensaje de recordatorio; las respuestas dentro de las 24 horas de
              un mensaje del cliente no se cobran.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Mercado Pago</CardTitle>
            <Badge tone="info">Muy pronto</Badge>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Tus clientes van a poder pagar con el link del recordatorio, y la factura se marca
            pagada sola. Mientras tanto, el link muestra tus{" "}
            <Link to="/configuracion#transferencia" className="text-primary underline-offset-4 hover:underline">
              datos para transferencia
            </Link>
            .
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TemplatesCard({ settings, canEdit }: { settings: ReminderSettings; canEdit: boolean }) {
  const [editing, setEditing] = useState<ReminderTemplate | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mensajes</CardTitle>
        <CardDescription>
          Cada mensaje es una plantilla que Meta revisa antes de que salga. Si lo cambiás, el
          anterior se sigue usando hasta que Meta apruebe el nuevo.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {settings.templates.map((template) => (
          <article
            key={template.kind}
            aria-label={template.label}
            className="flex flex-col gap-2 rounded-lg border p-3 sm:p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{template.label}</h3>
              <TemplateStatusBadge template={template} />
            </div>
            <p className="whitespace-pre-line rounded-md bg-muted/50 p-3 text-sm">{template.preview}</p>
            {template.newer_in_review ? (
              <p className="text-xs text-muted-foreground">
                Hay una versión nueva en revisión; mientras tanto sale la aprobada.
              </p>
            ) : null}
            {canEdit ? (
              <Button variant="outline" size="sm" className="self-start" onClick={() => setEditing(template)}>
                Editar texto
              </Button>
            ) : null}
          </article>
        ))}
      </CardContent>
      <TemplateDialog template={editing} fields={settings.fields} onClose={() => setEditing(null)} />
    </Card>
  );
}

function TemplateDialog({
  template,
  fields,
  onClose,
}: {
  template: ReminderTemplate | null;
  fields: string[];
  onClose: () => void;
}) {
  return (
    <Dialog open={template !== null} title={template ? `Editar: ${template.label}` : "Editar"} onClose={onClose}>
      {template ? (
        <TemplateForm key={template.kind} template={template} fields={fields} onDone={onClose} />
      ) : null}
    </Dialog>
  );
}

function TemplateForm({
  template,
  fields,
  onDone,
}: {
  template: ReminderTemplate;
  fields: string[];
  onDone: () => void;
}) {
  const textId = useId();
  const queryClient = useQueryClient();
  const [body, setBody] = useState(template.body);
  const save = useMutation({
    mutationFn: () => saveTemplateText(template.kind, body),
    onSuccess: (settings) => {
      queryClient.setQueryData(["reminders"], settings);
      onDone();
    },
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <label htmlFor={textId} className="text-sm font-medium">
        Texto del mensaje
      </label>
      <textarea
        id={textId}
        value={body}
        maxLength={1024}
        rows={6}
        onChange={(event) => setBody(event.target.value)}
        className="rounded-md border bg-card p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="flex flex-col gap-1 text-xs text-muted-foreground">
        <p>Podés usar estos datos (se completan solos):</p>
        <ul className="flex flex-wrap gap-2">
          {fields.map((field) => (
            <li key={field}>
              <button
                type="button"
                className="rounded border bg-muted px-2 py-1 font-mono"
                onClick={() => setBody(`${body.trimEnd()} {${field}}`)}
              >
                {`{${field}}`}
              </button>{" "}
              {FIELD_LABELS[field] ?? field}
            </li>
          ))}
        </ul>
        <p>
          Un dato no puede ir al principio ni al final, ni dos seguidos. Abajo va el botón “Ver y
          pagar” con el link de pago.
        </p>
      </div>
      {save.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(save.error, "No pudimos guardar el texto.")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !body.trim()}>
          {save.isPending ? "Enviando..." : "Enviar a revisión de Meta"}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          Volver
        </Button>
      </div>
    </form>
  );
}
