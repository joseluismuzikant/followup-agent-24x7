import type { BusinessActivity, BusinessRow } from "@followup/api-client-cuentas-claras";

export const PRODUCT_NAME = "Cuentas Claras";

export function planLabel(plan: BusinessRow["plan"]): string {
  if (plan.plan === "pro") {
    return "Pro";
  }
  const days = plan.trial_days_left ?? 0;
  return `Prueba · ${days} ${days === 1 ? "día" : "días"}`;
}

/** The panel's checklist items (the API's keys). */
export const checklistLabels: Record<string, string> = {
  account: "Cuenta creada",
  invoices: "Facturas cargadas",
  whatsapp: "WhatsApp conectado",
  mercado_pago: "Mercado Pago conectado",
  reminders: "Recordatorios configurados",
};

const actionLabels: Record<string, string> = {
  sign_up: "Se registró",
  tenant_created_by_admin: "Negocio dado de alta",
  owner_claimed: "El dueño entró por primera vez",
  owner_invited: "Invitación enviada al dueño",
  invitation_resent: "Invitación reenviada",
  temporary_password_reset: "Clave temporal nueva",
  invitation_accepted: "El dueño eligió su clave",
  tenant_suspended: "Cuenta suspendida",
  tenant_reactivated: "Cuenta reactivada",
  client_created: "Cargó un cliente",
  client_updated: "Editó un cliente",
  invoice_created: "Cargó una factura",
  invoice_updated: "Editó una factura",
  invoice_paid: "Marcó una factura como pagada",
  invoice_cancelled: "Anuló una factura",
  invoices_imported: "Importó facturas",
};

const paidViaLabels: Record<string, string> = {
  manual: "efectivo o cheque",
  transfer: "transferencia",
  mercado_pago: "Mercado Pago",
  other: "otro medio",
};

/** One line per event. Details are ids and counts only (never names or amounts). */
export function activityText(event: BusinessActivity): string {
  const label = actionLabels[event.action] ?? event.action;
  const details = event.details;
  const extra: string[] = [];
  if (details.created !== undefined && details.created !== null) {
    extra.push(
      `${String(details.created)} nuevas, ${String(details.updated ?? 0)} actualizadas, ${String(details.failed ?? 0)} con errores`,
    );
  }
  if (typeof details.paid_via === "string") {
    extra.push(paidViaLabels[details.paid_via] ?? details.paid_via);
  }
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
const ars = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  maximumFractionDigits: 0,
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function formatDate(iso: string): string {
  return dateOnly.format(new Date(iso));
}

/** Open amounts come as decimal strings ("5400000.00"), in pesos. */
export function formatPesos(amount: string): string {
  return ars.format(Number(amount));
}

export function navItems(pathname: string) {
  return [
    {
      label: "Negocios",
      href: "/",
      active: pathname === "/" || pathname.startsWith("/negocios"),
    },
  ];
}
