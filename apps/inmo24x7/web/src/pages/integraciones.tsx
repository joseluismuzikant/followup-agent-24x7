import type {
  IntegrationDelivery,
  Integrations,
  SyncReport,
  TokkoIntegration,
  WebhookIntegration,
  WidgetInput,
  WidgetIntegration,
} from "@followup/api-client-inmo24x7";
import {
  Badge,
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
import { useId, useState } from "react";
import { Link } from "react-router";

import {
  connectTokko,
  deleteWebhook,
  disconnectTokko,
  fetchIntegrations,
  rotateWebhookSecret,
  saveWebhook,
  saveWidget,
  syncTokko,
  testWebhook,
  updateTokko,
} from "../api/integrations";
import { fetchMe } from "../api/me";
import { apiErrorMessage } from "../lib/api-errors";
import {
  HEX_COLOR,
  deliveryStatusLabels,
  deliveryStatusTones,
  integrationErrorLabel,
  widgetMessage,
  widgetSnippet,
} from "../lib/integrations";
import { formatDateTime } from "../lib/leads";
import { canEditSetup } from "../lib/setup";

const QUERY_KEY = ["integrations"];

/** Configuración → Integraciones: Tokko Broker, the lead webhook and the website button. */
export function IntegracionesPage() {
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchIntegrations,
    // While a sync is on its way, check every few seconds.
    refetchInterval: (current) =>
      current.state.data?.tokko.last_sync_status === "queued" ? 3000 : false,
  });
  if (!query.data || !meQuery.data) {
    return null;
  }
  const readOnly = !canEditSetup(meQuery.data.profile.role);
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <Link to="/configuracion" className="text-sm text-brand underline-offset-4 hover:underline">
        ← Volver a Configuración
      </Link>
      {readOnly ? (
        <p className="text-sm text-muted-foreground">
          Solo el dueño o un encargado pueden cambiar las integraciones.
        </p>
      ) : null}
      <TokkoCard tokko={query.data.tokko} readOnly={readOnly} />
      <WebhookCard webhook={query.data.webhook} readOnly={readOnly} />
      <WidgetCard widget={query.data.widget} readOnly={readOnly} />
    </div>
  );
}

function useSave<T, R>(mutationFn: (value: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data) => {
      if (data && typeof data === "object" && "tokko" in data) {
        queryClient.setQueryData(QUERY_KEY, data as unknown as Integrations);
      } else {
        void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      }
    },
  });
}

function ErrorLine({ error }: { error: unknown }) {
  if (!error) {
    return null;
  }
  return (
    <p className="text-sm text-destructive" role="alert">
      {apiErrorMessage(error, "No pudimos guardar los cambios. Probá de nuevo.")}
    </p>
  );
}

function Check({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex items-start gap-2 text-sm">
      <input
        id={id}
        type="checkbox"
        className="mt-1 size-4"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <span className="block font-medium">{label}</span>
        <span className="text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}

// --- Tokko ---------------------------------------------------------------------------------

function TokkoCard({ tokko, readOnly }: { tokko: TokkoIntegration; readOnly: boolean }) {
  const [key, setKey] = useState("");
  const connect = useSave((value: string) => connectTokko(value));
  const options = useSave((value: { import_properties: boolean; send_leads: boolean }) =>
    updateTokko(value),
  );
  const disconnect = useSave(() => disconnectTokko());
  const sync = useSave(() => syncTokko());
  const syncing = tokko.last_sync_status === "queued";

  return (
    <Card id="tokko">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Tokko Broker</CardTitle>
          <Badge tone={tokko.connected ? "success" : "neutral"}>
            {tokko.connected ? "Conectado" : "Sin conectar"}
          </Badge>
        </div>
        <CardDescription>
          Tus propiedades entran solas desde Tokko y cada consulta que Sofía deriva a tu equipo
          llega a Tokko como contacto web.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {!tokko.connected ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (key.trim()) {
                connect.mutate(key.trim(), { onSuccess: () => setKey("") });
              }
            }}
          >
            <FormField
              label="Clave API de Tokko"
              htmlFor="tokko-key"
              hint="En Tokko: Mi empresa → Permisos → Clave API. La guardamos cifrada y no se vuelve a mostrar."
            >
              <Input
                id="tokko-key"
                type="password"
                autoComplete="off"
                value={key}
                disabled={readOnly}
                onChange={(event) => setKey(event.target.value)}
              />
            </FormField>
            <ErrorLine error={connect.error} />
            {readOnly ? null : (
              <Button
                type="submit"
                className="self-start"
                disabled={connect.isPending || !key.trim()}
              >
                {connect.isPending ? "Probando..." : "Probar conexión"}
              </Button>
            )}
          </form>
        ) : (
          <>
            <div className="flex flex-col gap-3">
              <Check
                label="Importar propiedades"
                hint="Cada 6 horas. Lo que pausás o sacás en Tokko se pausa acá."
                checked={tokko.import_properties}
                disabled={readOnly || options.isPending}
                onChange={(value) =>
                  options.mutate({ import_properties: value, send_leads: tokko.send_leads })
                }
              />
              <Check
                label="Enviar consultas a Tokko"
                hint="Cuando Sofía deriva una consulta (pidió visita, completó los datos o pidió hablar con alguien)."
                checked={tokko.send_leads}
                disabled={readOnly || options.isPending}
                onChange={(value) =>
                  options.mutate({ import_properties: tokko.import_properties, send_leads: value })
                }
              />
            </div>
            <ErrorLine error={options.error ?? sync.error ?? disconnect.error} />
            <SyncStatus tokko={tokko} />
            {readOnly ? null : (
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => sync.mutate(undefined)}
                  disabled={syncing || sync.isPending || !tokko.import_properties}
                >
                  {syncing ? "Sincronizando..." : "Sincronizar ahora"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => disconnect.mutate(undefined)}
                  disabled={disconnect.isPending}
                >
                  Desconectar
                </Button>
              </div>
            )}
            <DeliveryLog title="Últimos envíos a Tokko" items={tokko.deliveries} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SyncStatus({ tokko }: { tokko: TokkoIntegration }) {
  const report = tokko.last_report;
  if (tokko.last_sync_status === "queued") {
    return (
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Sincronizando con Tokko…
      </p>
    );
  }
  if (!report) {
    return null;
  }
  return (
    <section aria-label="Última sincronización" className="rounded-lg border p-3 text-sm">
      <p className="font-medium">
        Última sincronización: {formatDateTime(report.finished_at)}
      </p>
      {report.error_code ? (
        <p className="mt-1 text-destructive" role="alert">
          No se pudo completar: {integrationErrorLabel(report.error_code)}.
          {report.error_code === "tokko_key_invalid"
            ? " Desconectá y volvé a conectar con la clave nueva."
            : " Lo volvemos a intentar en la próxima sincronización."}
        </p>
      ) : null}
      <SyncCounts report={report} />
      {report.failed.length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer">
            {report.failed.length === 1
              ? "1 propiedad no se pudo importar"
              : `${report.failed.length} propiedades no se pudieron importar`}
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-muted-foreground">
            {report.failed.map((item) => (
              <li key={`${item.external_id}-${item.reason}`}>
                {item.title} (Tokko {item.external_id}): {item.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function SyncCounts({ report }: { report: SyncReport }) {
  const parts = [
    `${report.created} nuevas`,
    `${report.updated} actualizadas`,
    `${report.paused} pausadas`,
    `${report.unchanged} sin cambios`,
  ];
  return <p className="mt-1 text-muted-foreground">{parts.join(" · ")}</p>;
}

function DeliveryLog({ title, items }: { title: string; items: IntegrationDelivery[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{title}</h3>
      <ul className="flex flex-col divide-y rounded-lg border text-sm">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
            <span className="min-w-0">
              <span className="block">
                {item.event === "ping" ? "Prueba" : "Consulta derivada"} ·{" "}
                {formatDateTime(item.created_at)}
              </span>
              {item.error_code ? (
                <span className="block text-xs text-muted-foreground">
                  {integrationErrorLabel(item.error_code)}
                </span>
              ) : null}
            </span>
            <span className="flex items-center gap-2">
              {item.status_code ? (
                <span className="text-xs text-muted-foreground">HTTP {item.status_code}</span>
              ) : null}
              <Badge tone={deliveryStatusTones[item.status]}>
                {deliveryStatusLabels[item.status]}
              </Badge>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- Webhook -------------------------------------------------------------------------------

function WebhookCard({ webhook, readOnly }: { webhook: WebhookIntegration; readOnly: boolean }) {
  const [url, setUrl] = useState(webhook.url ?? "");
  const [secret, setSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const save = useSave((value: { url: string; enabled: boolean }) =>
    saveWebhook(value.url, value.enabled),
  );
  const rotate = useSave(() => rotateWebhookSecret());
  const remove = useSave(() => deleteWebhook());
  const test = useSave(() => testWebhook());

  function shown(result: unknown) {
    const value = (result as { secret?: string | null }).secret;
    if (value) {
      setSecret(value);
      setCopied(false);
    }
  }

  return (
    <Card id="webhook">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Webhook de consultas</CardTitle>
          <Badge tone={webhook.enabled ? "success" : "neutral"}>
            {webhook.enabled ? "Activo" : "Inactivo"}
          </Badge>
        </div>
        <CardDescription>
          Para cualquier otro CRM, Zapier o Make: te mandamos cada consulta derivada a tu equipo
          como JSON firmado.{" "}
          <a
            className="text-brand underline-offset-4 hover:underline"
            href="https://github.com/joseluismuzikant/followup-agent-24x7/blob/master/docs/integrations.md"
            target="_blank"
            rel="noreferrer"
          >
            Ver el formato
          </a>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate({ url: url.trim(), enabled: true }, { onSuccess: shown });
          }}
        >
          <FormField label="Dirección (https://)" htmlFor="webhook-url">
            <Input
              id="webhook-url"
              type="url"
              inputMode="url"
              placeholder="https://hooks.zapier.com/hooks/catch/…"
              value={url}
              disabled={readOnly}
              onChange={(event) => setUrl(event.target.value)}
            />
          </FormField>
          <ErrorLine error={save.error ?? rotate.error ?? remove.error ?? test.error} />
          {readOnly ? null : (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={save.isPending || !url.trim()}>
                {save.isPending ? "Guardando..." : "Guardar"}
              </Button>
              {webhook.configured ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={test.isPending}
                    onClick={() => test.mutate(undefined)}
                  >
                    {test.isPending ? "Enviando..." : "Enviar prueba"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={rotate.isPending}
                    onClick={() => rotate.mutate(undefined, { onSuccess: shown })}
                  >
                    Generar secreto nuevo
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={remove.isPending}
                    onClick={() =>
                      remove.mutate(undefined, {
                        onSuccess: () => {
                          setUrl("");
                          setSecret(null);
                        },
                      })
                    }
                  >
                    Quitar
                  </Button>
                </>
              ) : null}
            </div>
          )}
        </form>
        {secret ? (
          <div className="rounded-lg border border-amber-200 bg-warning-soft p-3 text-sm" role="status">
            <p className="font-medium">Tu secreto (se muestra una sola vez)</p>
            <p className="mt-1 text-muted-foreground">
              Usalo para verificar la firma <code>X-Inmo24x7-Signature</code>.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="min-w-0 break-all rounded bg-card px-2 py-1 text-xs">{secret}</code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard?.writeText(secret);
                  setCopied(true);
                }}
              >
                {copied ? "Copiado" : "Copiar"}
              </Button>
            </div>
          </div>
        ) : webhook.has_secret ? (
          <p className="text-sm text-muted-foreground">
            El secreto ya está generado. Si lo perdiste, generá uno nuevo.
          </p>
        ) : null}
        {test.data ? (
          <p className="text-sm" aria-live="polite">
            {test.data.status === "delivered"
              ? `La prueba llegó (HTTP ${test.data.status_code}).`
              : `La prueba falló: ${integrationErrorLabel(test.data.error_code)}${
                  test.data.status_code ? ` (HTTP ${test.data.status_code})` : ""
                }.`}
          </p>
        ) : null}
        <DeliveryLog title="Últimos envíos" items={webhook.deliveries} />
      </CardContent>
    </Card>
  );
}

// --- Website button ------------------------------------------------------------------------

function WidgetCard({ widget, readOnly }: { widget: WidgetIntegration; readOnly: boolean }) {
  const [color, setColor] = useState(widget.color);
  const [textColor, setTextColor] = useState(widget.text_color);
  const [label, setLabel] = useState(widget.label);
  const [position, setPosition] = useState(widget.position);
  const [copied, setCopied] = useState(false);
  const save = useSave((input: WidgetInput) => saveWidget(input));
  const snippet = widgetSnippet(window.location.origin, widget.public_id);
  const valid = HEX_COLOR.test(color) && HEX_COLOR.test(textColor) && label.trim().length > 0;

  return (
    <Card id="boton">
      <CardHeader>
        <CardTitle>Botón para tu web</CardTitle>
        <CardDescription>
          Un botón «Consultar por WhatsApp» que abre la conversación con Sofía con la propiedad ya
          identificada. Sin cookies ni seguimiento.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {!widget.whatsapp_connected ? (
          <p className="rounded-lg border border-amber-200 bg-warning-soft p-3 text-sm" role="status">
            El botón aparece cuando tu WhatsApp está conectado.
          </p>
        ) : null}
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium" id="snippet-label">
            Pegá esta línea en tu web
          </p>
          <pre
            aria-labelledby="snippet-label"
            className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border bg-muted p-3 text-xs"
          >
            {snippet}
          </pre>
          <Button
            variant="outline"
            className="self-start"
            onClick={() => {
              void navigator.clipboard?.writeText(snippet);
              setCopied(true);
            }}
          >
            {copied ? "Copiado" : "Copiar"}
          </Button>
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Cómo instalarlo</summary>
          <div className="mt-2 flex flex-col gap-2 text-muted-foreground">
            <p>
              <strong>Web hecha con Tokko:</strong> en Tokko, entrá a la configuración de tu sitio
              web y pegá la línea en la sección de código personalizado (o en Google Tag Manager,
              como «HTML personalizado» en todas las páginas).
            </p>
            <p>
              <strong>Cualquier otra web:</strong> pegala antes de <code>&lt;/body&gt;</code> en
              todas las páginas (WordPress: un plugin de «insertar código en el pie»).
            </p>
            <p>
              <strong>En la página de una propiedad</strong> el botón usa la dirección de la página.
              Si podés, marcala con <code>data-propiedad="CÓDIGO"</code> en cualquier elemento
              (el código de Tokko, el link o el id de inmo24x7).
            </p>
          </div>
        </details>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate({
              enabled: true,
              color,
              text_color: textColor,
              position,
              label: label.trim(),
            });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <ColorField id="widget-color" label="Color del botón" value={color} onChange={setColor} disabled={readOnly} />
            <ColorField
              id="widget-text-color"
              label="Color del texto"
              value={textColor}
              onChange={setTextColor}
              disabled={readOnly}
            />
          </div>
          <FormField label="Texto del botón" htmlFor="widget-label">
            <Input
              id="widget-label"
              maxLength={40}
              value={label}
              disabled={readOnly}
              onChange={(event) => setLabel(event.target.value)}
            />
          </FormField>
          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="font-medium">Posición</legend>
            <div className="flex gap-4">
              {(["right", "left"] as const).map((value) => (
                <label key={value} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="widget-position"
                    value={value}
                    checked={position === value}
                    disabled={readOnly}
                    onChange={() => setPosition(value)}
                  />
                  {value === "right" ? "Abajo a la derecha" : "Abajo a la izquierda"}
                </label>
              ))}
            </div>
          </fieldset>
          <WidgetPreview color={color} textColor={textColor} label={label} position={position} />
          <ErrorLine error={save.error} />
          {save.isSuccess && !save.error ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Guardado. Tu web lo toma en unos minutos.
            </p>
          ) : null}
          {readOnly ? null : (
            <Button type="submit" className="self-start" disabled={save.isPending || !valid}>
              {save.isPending ? "Guardando..." : "Guardar botón"}
            </Button>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function ColorField({
  id,
  label,
  value,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <FormField label={label} htmlFor={id}>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} (selector)`}
          className="h-10 w-12 shrink-0 cursor-pointer rounded border bg-card"
          value={HEX_COLOR.test(value) ? value : "#000000"}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        <Input id={id} value={value} maxLength={7} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      </div>
    </FormField>
  );
}

/** What visitors see: the button over a sketch of a property page. */
function WidgetPreview({
  color,
  textColor,
  label,
  position,
}: {
  color: string;
  textColor: string;
  label: string;
  position: "right" | "left";
}) {
  const background = HEX_COLOR.test(color) ? color : "#047857";
  const foreground = HEX_COLOR.test(textColor) ? textColor : "#ffffff";
  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">Vista previa</figcaption>
      <div className="relative h-40 overflow-hidden rounded-lg border bg-muted" aria-hidden="true">
        <div className="space-y-2 p-3">
          <div className="h-3 w-2/3 rounded bg-border" />
          <div className="h-3 w-1/2 rounded bg-border" />
          <div className="h-16 w-full rounded bg-border/60" />
        </div>
        <span
          className="absolute bottom-3 inline-flex max-w-[85%] items-center gap-2 truncate rounded-full px-4 py-2 text-sm font-semibold shadow-lg"
          style={{
            background,
            color: foreground,
            [position === "right" ? "right" : "left"]: "12px",
          }}
        >
          <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="currentColor" aria-hidden="true">
            <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Z" />
          </svg>
          {label.trim() || "Consultar por WhatsApp"}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        En la página de una propiedad abre WhatsApp con: «{widgetMessage("2 ambientes luminoso", "TKO1234")}»
      </p>
    </figure>
  );
}
