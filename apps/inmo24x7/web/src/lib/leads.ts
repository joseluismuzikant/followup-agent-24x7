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

/** "hace 5 minutos", "ayer" (@followup/app-shell). */
export { timeAgo } from "@followup/app-shell";

/** List ages: "recién", "12 min", "3 h", "Ayer", "4 días". */
export function age(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) {
    return "recién";
  }
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} h`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? "Ayer" : `${days} días`;
}

/** Response time: "6 s", "1 min 20 s", "2 min"; "—" without data. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "—";
  }
  const total = Math.round(seconds);
  if (total < 60) {
    return `${total} s`;
  }
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export const BUSINESS_TIMEZONE = "America/Argentina/Buenos_Aires";

const clock = new Intl.DateTimeFormat("es-AR", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: BUSINESS_TIMEZONE,
});

/** "18:40" in the business's timezone. */
export function formatTime(iso: string): string {
  return clock.format(new Date(iso));
}

const parts = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: BUSINESS_TIMEZONE,
});

/** An ISO instant as the value of an <input type="datetime-local"> in Buenos Aires time. */
export function toLocalInput(iso: string): string {
  const values = Object.fromEntries(
    parts.formatToParts(new Date(iso)).map((part) => [part.type, part.value]),
  );
  const hour = values.hour === "24" ? "00" : values.hour;
  return `${values.year}-${values.month}-${values.day}T${hour}:${values.minute}`;
}

/** An <input type="datetime-local"> value in Buenos Aires time (UTC-3, no DST) as ISO. */
export function fromLocalInput(value: string): string {
  return new Date(`${value}:00-03:00`).toISOString();
}

/** Owner, manager and agent take over, reply and confirm visits; a viewer only reads. */
export function canActOnLeads(role: string): boolean {
  return role === "owner" || role === "manager" || role === "agent";
}

/** A lead's name, else its phone or email. */
export function leadName(lead: { visitor_name: string | null; contact: string | null }): string {
  return lead.visitor_name ?? lead.contact ?? "Sin nombre todavía";
}
