import type {
  Client,
  ClientDetail,
  ImportReport,
  Invoice,
  InvoiceDetail,
  InvoiceList,
  MeResponse,
  OnboardingState,
  ReminderSettings,
  ReminderTemplate,
  Summary,
} from "@followup/api-client-cuentas-claras";

const order = ["business", "invoices", "reminders", "connect", "done"];

export function onboardingState(
  currentStep: string,
  overrides: { invoicesLoaded?: boolean } = {},
): OnboardingState {
  const loaded = overrides.invoicesLoaded ?? false;
  return {
    current_step: currentStep,
    completed_steps: order
      .slice(0, order.indexOf(currentStep))
      .map((step) => ({ step, completed_at: "2026-11-02T12:00:00Z" })),
    finished: currentStep === "done",
    checklist: {
      items: [
        { key: "account", done: true },
        { key: "invoices", done: loaded },
        { key: "whatsapp", done: false },
        { key: "mercado_pago", done: false },
        { key: "reminders", done: false },
      ],
      ready_count: loaded ? 2 : 1,
      total: 5,
      facts: {
        account_created: true,
        invoices_loaded: loaded,
        whatsapp_connected: false,
        mercado_pago_connected: false,
        reminders_configured: false,
      },
    },
  };
}

export function me(role = "owner"): MeResponse {
  return {
    profile: {
      id: "11111111-1111-1111-1111-111111111111",
      email: "dueno@ascensoresdelta.test",
      display_name: "dueno@ascensoresdelta.test",
      tenant_id: "22222222-2222-2222-2222-222222222222",
      role,
      is_platform_admin: false,
    },
    tenant: {
      id: "22222222-2222-2222-2222-222222222222",
      name: "Ascensores Delta",
      slug: "ascensores-delta",
      status: "active",
      plan: "trial",
      trial_ends_at: "2099-01-01T00:00:00Z",
      created_at: "2026-11-02T12:00:00Z",
    },
    support_email: "soporte@cuentasclaras.test",
  };
}

export function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    to_collect: { amount: "5400000.00", count: 32 },
    overdue: { amount: "2100000.00", count: 13 },
    to_collect_usd: { amount: "0.00", count: 0 },
    overdue_usd: { amount: "0.00", count: 0 },
    ...overrides,
  };
}

export function invoice(overrides: Partial<Invoice> = {}): Invoice {
  return {
    id: "inv-1",
    client_id: "cli-1",
    client_name: "Consorcio Rivadavia 4500",
    client_subtitle: "Av. Rivadavia 4500",
    number: "B 0003-00001245",
    amount: "180000.00",
    currency: "ARS",
    due_date: "2026-10-10",
    status: { kind: "overdue", label: "Vencida · 23 días", days_overdue: 23 },
    next_action: null,
    next_action_kind: null,
    ...overrides,
  };
}

export function invoiceList(items: Invoice[], overrides: Partial<InvoiceList> = {}): InvoiceList {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 25,
    total_pages: items.length ? 1 : 0,
    counts: { pending: 32, overdue: 13, promised: 0, paid_this_month: 8 },
    ...overrides,
  };
}

export function client(overrides: Partial<ClientDetail> = {}): ClientDetail {
  return {
    id: "cli-1",
    name: "Consorcio Rivadavia 4500",
    subtitle: "Av. Rivadavia 4500",
    cuit: "30-71234567-1",
    contact_name: "Marta Gómez",
    whatsapp: "+5491155551234",
    whatsapp_display: "+54 9 11 5555-1234",
    email: null,
    notes: null,
    active: true,
    no_reminders: false,
    missing_whatsapp: false,
    open_invoices: 2,
    owed_ars: "360000.00",
    owed_usd: "0.00",
    created_at: "2026-11-02T12:00:00Z",
    invoices: [],
    ...overrides,
  };
}

export function invoiceDetail(overrides: Partial<InvoiceDetail> = {}): InvoiceDetail {
  const owner: Client = { ...client() };
  delete (owner as Partial<ClientDetail>).invoices;
  return {
    id: "inv-1",
    number: "B 0003-00001245",
    invoice_type: "B",
    point_of_sale: 3,
    invoice_number: 1245,
    issue_date: "2026-09-30",
    due_date: "2026-10-10",
    amount: "180000.00",
    currency: "ARS",
    description: "Abono mantenimiento septiembre",
    status: { kind: "overdue", label: "Vencida · 23 días", days_overdue: 23 },
    lifecycle: "open",
    payment: null,
    cancelled_reason: null,
    promised_until: null,
    client: owner,
    next_action: null,
    next_action_kind: null,
    ...overrides,
  };
}

export const errorsReport: ImportReport = {
  id: "imp-1",
  file_name: "facturas-con-errores.csv",
  total: 40,
  created: 35,
  updated: 0,
  skipped: 1,
  failed: 4,
  errors: [
    { row: 7, error: "Fila 7: el CUIT no es válido." },
    { row: 12, error: "Fila 12: falta el vencimiento." },
    { row: 20, error: "Fila 20: la fecha tiene que ser dd/mm/aaaa." },
    { row: 31, error: "Fila 31: el monto no es un número." },
  ],
  warnings: ["Fila 9: la factura ya figuraba pagada; no la cambiamos."],
};

export function reminderTemplate(
  kind: ReminderTemplate["kind"],
  overrides: Partial<ReminderTemplate> = {},
): ReminderTemplate {
  const labels = {
    before: "Antes del vencimiento",
    due: "El día del vencimiento",
    after: "Después del vencimiento",
    several: "Varias facturas del mismo cliente",
  } as const;
  return {
    kind,
    label: labels[kind],
    body: "Hola {cliente}, te escribimos de {negocio}. La factura {factura} vence pronto.",
    preview: `Hola Edificio Güemes, te escribimos de Ascensores Delta (${kind}).`,
    version: 1,
    status: "approved",
    status_label: "aprobada",
    rejection_reason: null,
    in_use_version: 1,
    newer_in_review: false,
    ...overrides,
  };
}

export function reminderSettings(overrides: Partial<ReminderSettings> = {}): ReminderSettings {
  return {
    steps: [
      { id: "s1", offset_days: -3, kind: "reminder", template_kind: "before", active: true, label: "3 días antes" },
      { id: "s2", offset_days: 0, kind: "reminder", template_kind: "due", active: true, label: "El día del vencimiento" },
      { id: "s3", offset_days: 7, kind: "reminder", template_kind: "after", active: true, label: "7 días después" },
      {
        id: "s4",
        offset_days: 15,
        kind: "escalate",
        template_kind: null,
        active: true,
        label: "15 días después: avisar al dueño",
      },
    ],
    window: { preset: "mornings", start: null, end: null },
    skip_holidays: true,
    pause_on_promise: true,
    configured: false,
    templates: (["before", "due", "after", "several"] as const).map((kind) => reminderTemplate(kind)),
    whatsapp: { status: "connected", display_phone_number: "+54 9 11 5555-0200" },
    month_count: 3,
    upcoming_holidays: ["2026-11-23", "2026-12-07"],
    fields: ["cliente", "negocio", "factura", "monto", "vencimiento"],
    ...overrides,
  };
}
