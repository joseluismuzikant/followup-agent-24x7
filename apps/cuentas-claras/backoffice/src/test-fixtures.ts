import type { BusinessDetail, BusinessList, BusinessRow } from "@followup/api-client-cuentas-claras";

export function businessRow(overrides: Partial<BusinessRow> = {}): BusinessRow {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    name: "Ascensores Delta",
    status: "active",
    owner_email: "dueno@ascensoresdelta.test",
    owner_pending: false,
    plan: { plan: "trial", trial_days_left: 12 },
    onboarding_done: 2,
    onboarding_total: 5,
    clients: 25,
    open_amount: "5400000.00",
    created_at: "2026-11-02T12:00:00Z",
    ...overrides,
  };
}

export function businessList(items: BusinessRow[] = [businessRow()]): BusinessList {
  return { items, total: items.length, page: 1, page_size: 25 };
}

export function businessDetail(overrides: Partial<BusinessDetail> = {}): BusinessDetail {
  return {
    ...businessRow(),
    suspended_reason: null,
    checklist: [
      { key: "account", done: true },
      { key: "invoices", done: true },
      { key: "whatsapp", done: false },
      { key: "mercado_pago", done: false },
      { key: "reminders", done: false },
    ],
    activity: [
      {
        at: "2026-11-02T13:00:00Z",
        actor_kind: "user",
        actor_name: "dueno@ascensoresdelta.test",
        action: "invoices_imported",
        details: { created: 40, updated: 0, failed: 0 },
      },
      {
        at: "2026-11-02T14:00:00Z",
        actor_kind: "user",
        actor_name: "dueno@ascensoresdelta.test",
        action: "invoice_paid",
        details: { invoice_id: "inv-1", paid_via: "transfer" },
      },
    ],
    ...overrides,
  };
}
