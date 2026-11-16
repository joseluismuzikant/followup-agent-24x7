import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { WhatsAppStatusCard as SharedStatusCard } from "@followup/app-shell";
import type { WhatsAppCopy } from "@followup/app-shell";

/** inmo24x7's words in S4: its agent answers on the number. */
export const INMO_WHATSAPP_COPY: WhatsAppCopy = {
  steps: [
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
  ],
  testMessage: {
    waiting: "Escribile a tu número desde otro teléfono: tu agente te va a responder",
    received: "Recibido: tu agente ya respondió",
  },
  verificationPending: "Meta está verificando tu empresa. Mientras tanto, tu agente ya responde.",
};

/** S4: how the WhatsApp connection is doing, in plain words (@followup/app-shell). */
export function WhatsAppStatusCard({ status }: { status: WhatsAppStatus }) {
  return <SharedStatusCard status={status} copy={INMO_WHATSAPP_COPY} />;
}
