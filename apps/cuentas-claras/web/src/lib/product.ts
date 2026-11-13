/** Cuentas Claras's onboarding and business types (the API validates the same values). */

export const PRODUCT_NAME = "Cuentas Claras";
export const TAGLINE = "Cobrá sin reclamar.";

export const businessTypes = [
  { value: "mantenimiento", label: "Mantenimiento (ascensores, matafuegos, climatización)" },
  { value: "seguridad", label: "Seguridad y monitoreo" },
  { value: "soporte_it", label: "Soporte IT" },
  { value: "agencia", label: "Agencia con abonos" },
  { value: "otro", label: "Otro servicio mensual" },
] as const;

export const wizardSteps = [
  { id: "business", path: "tu-negocio", label: "Tu negocio" },
  { id: "invoices", path: "tus-facturas", label: "Tus facturas" },
  { id: "reminders", path: "recordatorios", label: "Recordatorios" },
  { id: "connect", path: "conectar", label: "Conectar" },
  { id: "done", path: "listo", label: "Listo" },
] as const;

export type WizardStepId = (typeof wizardSteps)[number]["id"];

export function stepIndex(id: string): number {
  return wizardSteps.findIndex((step) => step.id === id);
}

export function stepPath(id: WizardStepId): string {
  return `/onboarding/${wizardSteps[stepIndex(id)]!.path}`;
}

export function stepFromPath(path: string | undefined) {
  return wizardSteps.find((step) => step.path === path);
}

/** The panel's checklist (the API sends the keys and whether each is done). */
export const checklistLabels: Record<string, { label: string; href?: string }> = {
  account: { label: "Cuenta creada" },
  invoices: { label: "Cargar tus facturas", href: "/facturas" },
  whatsapp: { label: "Conectar WhatsApp", href: "/configuracion#whatsapp" },
  mercado_pago: { label: "Conectar Mercado Pago (muy pronto)" },
  reminders: { label: "Configurar los recordatorios", href: "/recordatorios" },
};
