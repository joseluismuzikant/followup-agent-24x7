import type { BusinessActivity, BusinessRow } from "@followup/api-client-inmo24x7";

export const badgeLabels: Record<BusinessRow["whatsapp"], string> = {
  connected: "Conectado",
  verification_pending: "Verificación pendiente",
  action_required: "Acción requerida",
  not_connected: "Sin conectar",
};

export const badgeTones: Record<BusinessRow["whatsapp"], "success" | "warning" | "danger" | "neutral"> = {
  connected: "success",
  verification_pending: "warning",
  action_required: "danger",
  not_connected: "neutral",
};

export function planLabel(plan: BusinessRow["plan"]): string {
  if (plan.plan === "pro") {
    return "Pro";
  }
  const days = plan.trial_days_left ?? 0;
  return `Prueba · ${days} ${days === 1 ? "día" : "días"}`;
}

export const onboardingLabels: Record<string, string> = {
  account: "Cuenta creada",
  agent_configured: "Agente configurado",
  agent_tested: "Agente probado",
  whatsapp_connected: "WhatsApp conectado",
  own_properties: "Propiedades propias",
};

export const roleLabels: Record<string, string> = {
  owner: "Dueño",
  manager: "Encargado",
  agent: "Agente",
  viewer: "Solo lectura",
};

const actionLabels: Record<string, string> = {
  sign_up: "Se registró",
  tenant_created_by_admin: "Negocio dado de alta",
  owner_claimed: "El dueño entró por primera vez",
  agent_config_saved: "Guardó el agente",
  properties_imported: "Importó propiedades",
  whatsapp_connected: "Conectó WhatsApp",
  whatsapp_disconnected: "Desconectó WhatsApp",
  whatsapp_error: "WhatsApp dejó de funcionar",
  whatsapp_recovered: "WhatsApp volvió a funcionar",
  whatsapp_signup_failed: "Falló la conexión con Meta",
  whatsapp_signup_abandoned: "Dejó la conexión con Meta a mitad de camino",
  whatsapp_account_update: "Aviso de Meta sobre la cuenta",
  webhook_failure: "Falló un aviso de Meta",
  send_failure: "Un mensaje no salió",
  tenant_suspended: "Cuenta suspendida",
  tenant_reactivated: "Cuenta reactivada",
  reconnect_link_sent: "Se envió el link para reconectar",
  llm_cost_alert: "El consumo de LLM del mes pasó el aviso",
};

export function activityText(event: BusinessActivity): string {
  const label = actionLabels[event.action] ?? event.action;
  const details = event.details;
  const extra: string[] = [];
  if (details.version) extra.push(`versión ${details.version}`);
  if (details.created !== undefined && details.created !== null) {
    extra.push(`${details.created} nuevas, ${details.updated ?? 0} actualizadas, ${details.failed ?? 0} con errores`);
  }
  if (details.meta_code) extra.push(`código de Meta ${details.meta_code}`);
  if (details.step) extra.push(`paso ${details.step}`);
  if (details.event) extra.push(String(details.event));
  if (details.source === "manual") extra.push("a mano");
  if (details.cost_usd) extra.push(`USD ${details.cost_usd} en ${details.month}`);
  return extra.length ? `${label} · ${extra.join(" · ")}` : label;
}

export function actorText(event: BusinessActivity): string {
  if (event.actor_kind === "system") {
    return "Sistema";
  }
  const who = event.actor_name ?? "Alguien";
  return event.actor_kind === "admin" ? `${who} (admin)` : who;
}

const dateTime = new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("es-AR", { dateStyle: "medium" });

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function formatDate(iso: string): string {
  return dateOnly.format(new Date(iso));
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

const usd = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});
const share = new Intl.NumberFormat("es-AR", { style: "percent", maximumFractionDigits: 0 });
const count = new Intl.NumberFormat("es-AR");

/** API amounts come as decimal strings ("0.012345"). */
export function formatUsd(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : usd.format(Number(value));
}

/** Every call was of a model without a price: the cost is unknown, not zero. */
export function costUnknown(item: { llm_calls: number; unpriced_calls: number }): boolean {
  return item.llm_calls > 0 && item.unpriced_calls === item.llm_calls;
}

/** A cost, or "—" when no call of `item` had a price. */
export function formatCost(
  value: string | null | undefined,
  item: { llm_calls: number; unpriced_calls: number },
): string {
  return costUnknown(item) ? "—" : formatUsd(value);
}

export function formatShare(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : share.format(value);
}

export function formatCount(value: number): string {
  return count.format(value);
}

/** "2026-11" for the current UTC month (Consumo works in UTC months). */
export function currentMonth(now: Date = new Date()): string {
  return now.toISOString().slice(0, 7);
}

export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  const name = new Intl.DateTimeFormat("es-AR", { month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(year!, number! - 1, 1)),
  );
  return `${name} ${year}`;
}
