import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { Button } from "@followup/ui";

import { WhatsAppStatusCard } from "../WhatsAppStatusCard";
import { ConnectionErrorBanner } from "./ConnectionErrorBanner";
import { useEmbeddedSignup } from "./useEmbeddedSignup";

export const META_LINKS = {
  facebookHelp: "https://business.facebook.com/",
  verifyBusiness: "https://business.facebook.com/settings/security",
  paymentMethod: "https://business.facebook.com/wa/manage/home/",
};

const steps = [
  {
    title: "Entrá con tu cuenta de Facebook",
    text: "La que administra la página o el negocio de la inmobiliaria.",
  },
  {
    title: "Elegí el número",
    text: "Puede ser uno nuevo o el que ya usan. Si está en la app de WhatsApp Business, Meta te guía para pasarlo.",
  },
  {
    title: "Confirmá con el código por SMS",
    text: "Listo: nosotros configuramos todo lo demás.",
  },
];

/** S4, shared by wizard step 4 and Configuración → WhatsApp: Embedded Signup, the status
 * card, "Pendiente en Meta" and Meta's errors in plain Spanish. */
export function ConnectWhatsApp({ status }: { status: WhatsAppStatus | undefined }) {
  const { available, state, connect, retry } = useEmbeddedSignup();
  const current = state.phase === "connected" ? state.status : status;
  const connected = current !== undefined && current.status !== "not_connected";
  const busy = state.phase === "connecting" || state.phase === "finishing";
  const halfway = current?.signup_step && current.status !== "connected";

  return (
    <div className="flex flex-col gap-6">
      <ConnectionErrorBanner status={current} onReconnect={() => void connect()} />
      {connected && current ? (
        <>
          <WhatsAppStatusCard status={current} />
          <PendingOnMeta status={current} />
        </>
      ) : (
        <ol className="flex flex-col gap-3">
          {steps.map((item, position) => (
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

function PendingOnMeta({ status }: { status: WhatsAppStatus }) {
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
            : "Meta está verificando tu empresa. Mientras tanto, tu agente ya responde."
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
