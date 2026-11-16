import { Button, cn } from "@followup/ui";
import { Link } from "react-router";

import { timeAgo } from "../time";
import type { MetaConfig } from "./facebook";
import type { WhatsAppPanelApi, WhatsAppStatus } from "./types";
import { useEmbeddedSignup } from "./useEmbeddedSignup";
import type { DescribeError } from "./useEmbeddedSignup";

export const META_LINKS = {
  facebookHelp: "https://business.facebook.com/",
  verifyBusiness: "https://business.facebook.com/settings/security",
  paymentMethod: "https://business.facebook.com/wa/manage/home/",
};

/** What changes between products in S4: who answers on the number, and the steps' words. */
export interface WhatsAppCopy {
  steps: { title: string; text: string }[];
  /** "Mensaje de prueba" row: before and after the first inbound message. */
  testMessage: { waiting: string; received: string };
  /** "Pendiente en Meta" while the business verification is in review. */
  verificationPending: string;
}

export interface ConnectWhatsAppProps {
  status: WhatsAppStatus | undefined;
  api: WhatsAppPanelApi;
  config: MetaConfig | null;
  describeError: DescribeError;
  copy: WhatsAppCopy;
}

/** S4, shared by the wizard and Configuración → WhatsApp of every product: Embedded Signup,
 * the status card, "Pendiente en Meta" and Meta's errors in plain Spanish. */
export function ConnectWhatsApp({ status, api, config, describeError, copy }: ConnectWhatsAppProps) {
  const { available, state, connect, retry } = useEmbeddedSignup(api, config, describeError);
  const current = state.phase === "connected" ? state.status : status;
  const connected = current !== undefined && current.status !== "not_connected";
  const busy = state.phase === "connecting" || state.phase === "finishing";
  const halfway = current?.signup_step && current.status !== "connected";

  return (
    <div className="flex flex-col gap-6">
      <ConnectionErrorBanner status={current} onReconnect={() => void connect()} />
      {connected && current ? (
        <>
          <WhatsAppStatusCard status={current} copy={copy} />
          <PendingOnMeta status={current} copy={copy} />
        </>
      ) : (
        <ol className="flex flex-col gap-3">
          {copy.steps.map((item, position) => (
            <li key={item.title} className="flex gap-3 text-sm">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full border text-xs">
                {position + 1}
              </span>
              <span>
                <span className="block font-medium">{item.title}</span>
                <span className="text-muted-foreground">{item.text}</span>
              </span>
            </li>
          ))}
        </ol>
      )}

      {state.phase === "problem" ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <p className="font-medium">{state.title}</p>
          <p>{state.message}</p>
          {state.action ? <p>{state.action}</p> : null}
        </div>
      ) : halfway && current.signup_error ? (
        <div role="alert" className="flex flex-col gap-1 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <p className="font-medium">{current.signup_error.title}</p>
          <p>{current.signup_error.message}</p>
          <p>{current.signup_error.action}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        {!connected || current?.status === "error" || current?.status === "disconnected" ? (
          <Button disabled={!available || busy} onClick={() => void connect()}>
            {state.phase === "connecting"
              ? "Esperando a Meta..."
              : state.phase === "finishing"
                ? "Configurando tu número..."
                : current?.status === "error"
                  ? "Volver a conectar"
                  : "Conectar WhatsApp"}
          </Button>
        ) : null}
        {(state.phase === "problem" && state.canRetry) || (halfway && state.phase === "idle") ? (
          <Button variant="outline" disabled={busy} onClick={() => void retry()}>
            Reintentar configuración
          </Button>
        ) : null}
        {!connected ? (
          <a
            href={META_LINKS.facebookHelp}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            ¿No tenés cuenta de Facebook para empresas?
          </a>
        ) : null}
      </div>
      {!available && !connected ? (
        <p className="text-sm text-muted-foreground">
          La conexión con Meta no está configurada en este entorno. Escribinos y la conectamos
          por vos.
        </p>
      ) : null}
    </div>
  );
}

function PendingOnMeta({ status, copy }: { status: WhatsAppStatus; copy: WhatsAppCopy }) {
  const verification = status.business_verification;
  if (verification === "verified") {
    return null;
  }
  const known = verification === "pending" || verification === "failed";
  return (
    <section
      aria-label="Pendiente en Meta"
      className="flex flex-col gap-2 rounded-lg border border-dashed p-4 text-sm"
    >
      <p className="font-medium">Pendiente en Meta</p>
      <p className="text-muted-foreground">
        {known
          ? verification === "failed"
            ? "Meta no aprobó la verificación de tu empresa. Revisá qué te pide y volvé a enviarla."
            : copy.verificationPending
          : "Para que tu número funcione sin límites, Meta pide verificar la empresa y tener un medio de pago."}
      </p>
      <div className="flex flex-wrap gap-4">
        <a
          href={META_LINKS.verifyBusiness}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-4 hover:underline"
        >
          Verificar tu empresa
        </a>
        <a
          href={META_LINKS.paymentMethod}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-4 hover:underline"
        >
          Cargar un medio de pago
        </a>
      </div>
    </section>
  );
}

interface Row {
  label: string;
  value: string;
  ok: boolean;
}

function rows(status: WhatsAppStatus, copy: WhatsAppCopy): Row[] {
  const connected = status.status === "connected";
  const number = [status.display_phone_number, status.verified_name].filter(Boolean).join(" · ");
  const received = Boolean(status.last_inbound_at);
  return [
    {
      label: "Cuenta de Meta",
      value: status.error ? status.error.title : connected ? "Conectada" : "Desconectada",
      ok: connected,
    },
    { label: "Número", value: number || "Pendiente", ok: Boolean(status.display_phone_number) },
    {
      label: "Recepción de mensajes",
      value:
        received && status.last_inbound_at
          ? `Funcionando · último mensaje ${timeAgo(status.last_inbound_at)}`
          : "Esperando el primer mensaje",
      ok: received,
    },
    {
      label: "Mensaje de prueba",
      value: received ? copy.testMessage.received : copy.testMessage.waiting,
      ok: received,
    },
  ];
}

/** S4: how the WhatsApp connection is doing, in plain words. */
export function WhatsAppStatusCard({ status, copy }: { status: WhatsAppStatus; copy: WhatsAppCopy }) {
  return (
    <section aria-label="Estado de WhatsApp" className="flex flex-col gap-2 rounded-lg border p-4">
      {rows(status, copy).map((row) => (
        <div key={row.label} className="flex items-start gap-3 text-sm">
          <span
            aria-hidden="true"
            className={cn(
              "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs",
              row.ok ? "bg-emerald-100 text-emerald-800" : "bg-muted text-muted-foreground",
            )}
          >
            {row.ok ? "✓" : "•"}
          </span>
          <span>
            <span className="block font-medium">{row.label}</span>
            <span className="text-muted-foreground">{row.value}</span>
          </span>
        </div>
      ))}
    </section>
  );
}

/** Red banner on Inicio and Configuración while the WhatsApp connection is in error. */
export function ConnectionErrorBanner({
  status,
  onReconnect,
}: {
  status: WhatsAppStatus | undefined;
  /** Runs Embedded Signup in place; without it the button goes to Configuración. */
  onReconnect?: () => void;
}) {
  if (status?.status !== "error" || !status.error) {
    return null;
  }
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-rose-900"
    >
      <div className="flex flex-col gap-1 text-sm">
        <p className="font-medium">{status.error.title}</p>
        <p>
          {status.error.message}
          {status.failing_since
            ? ` Los mensajes no salen desde ${timeAgo(status.failing_since)}.`
            : ""}
        </p>
        <p>{status.error.action}</p>
      </div>
      {onReconnect ? (
        <Button variant="outline" size="sm" onClick={onReconnect}>
          Volver a conectar
        </Button>
      ) : (
        <Button asChild variant="outline" size="sm">
          <Link to="/configuracion#whatsapp">Volver a conectar</Link>
        </Button>
      )}
    </div>
  );
}
