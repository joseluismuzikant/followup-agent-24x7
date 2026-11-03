import type { DeliveryStatus, LeadStatus } from "@followup/api-client-inmo24x7";

/** S5 statuses. */
export const leadStatusLabels: Record<LeadStatus, string> = {
  qualifying: "Calificando",
  visit_proposed: "Visita propuesta",
  human_requested: "Pidió hablar con alguien",
  visit_confirmed: "Visita confirmada",
};

export const leadStatusTones: Record<LeadStatus, "info" | "warning" | "danger" | "success"> = {
  qualifying: "info",
  visit_proposed: "warning",
  human_requested: "danger",
  visit_confirmed: "success",
};

export const deliveryLabels: Record<DeliveryStatus, string> = {
  queued: "Enviando",
  sent: "Enviado",
  delivered: "Entregado",
  read: "Leído",
  failed: "No se pudo enviar",
};

/** What the visitor sent that the agent cannot read. */
export const contentTypeLabels: Record<string, string> = {
  audio: "Audio",
  voice: "Audio",
  image: "Imagen",
  video: "Video",
  document: "Documento",
  sticker: "Sticker",
  location: "Ubicación",
  contacts: "Contacto",
  unsupported: "Mensaje no compatible",
};

export function channelLabel(channel: string): string {
  return channel === "whatsapp" ? "por WhatsApp" : "en el simulador";
}

const dateTime = new Intl.DateTimeFormat("es-AR", {
  weekday: "long",
  day: "numeric",
  month: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Argentina/Buenos_Aires",
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

const relative = new Intl.RelativeTimeFormat("es-AR", { numeric: "auto" });

/** "hace 5 minutos", "ayer". */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return relative.format(Math.round(seconds / size), unit);
    }
  }
  return "recién";
}
