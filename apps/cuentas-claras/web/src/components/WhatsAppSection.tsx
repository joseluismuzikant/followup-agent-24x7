import { ConnectWhatsApp } from "@followup/app-shell";
import type { WhatsAppCopy } from "@followup/app-shell";
import { useQuery } from "@tanstack/react-query";

import { fetchWhatsAppStatus, panelApi } from "../api/whatsapp";
import { apiErrorMessage } from "../lib/api-errors";
import { metaConfig } from "../lib/facebook";

/** Cuentas Claras's words in S4: reminders go out from the number. */
export const WHATSAPP_COPY: WhatsAppCopy = {
  steps: [
    {
      title: "Entrá con tu cuenta de Facebook",
      text: "La que administra la página o el negocio de tu empresa.",
    },
    {
      title: "Elegí el número",
      text: "Los recordatorios salen desde ese número, con el nombre de tu negocio. Puede ser uno nuevo o el que ya usan.",
    },
    {
      title: "Confirmá con el código por SMS",
      text: "Listo: creamos los mensajes de recordatorio y Meta los revisa (suele tardar minutos).",
    },
  ],
  testMessage: {
    waiting: "Cuando un cliente responda un recordatorio, te avisamos por email",
    received: "Recibido: ya llegaron respuestas de tus clientes",
  },
  verificationPending:
    "Meta está verificando tu empresa. Mientras tanto, los recordatorios ya salen.",
};

export function useWhatsAppStatus() {
  return useQuery({ queryKey: ["whatsapp"], queryFn: fetchWhatsAppStatus });
}

/** Configuración → WhatsApp and the wizard's "Conectar". */
export function WhatsAppSection() {
  const status = useWhatsAppStatus();
  return (
    <ConnectWhatsApp
      status={status.data}
      api={panelApi}
      config={metaConfig()}
      describeError={apiErrorMessage}
      copy={WHATSAPP_COPY}
    />
  );
}
