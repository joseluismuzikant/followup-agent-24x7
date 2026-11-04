import type {
  BusinessDetail,
  BusinessList,
  BusinessRow,
  SystemHealth,
} from "@followup/api-client-inmo24x7";

export function businessRow(overrides: Partial<BusinessRow> = {}): BusinessRow {
  return {
    id: "6d57c8d4-6b5b-4fac-8e50-23b6f0c0f210",
    name: "Inmobiliaria Sur",
    status: "active",
    owner_email: "duena@sur.test",
    owner_pending: false,
    plan: { plan: "trial", name: "Prueba", trial_days_left: 12 },
    onboarding_done: 3,
    onboarding_total: 5,
    whatsapp: "connected",
    needs_help: false,
    leads_last_7_days: 7,
    created_at: "2026-10-26T15:17:45Z",
    ...overrides,
  };
}

export function businessList(items: BusinessRow[] = [businessRow()]): BusinessList {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 20,
    kpis: { active: 4, trial: 3, onboarding_unfinished: 2, whatsapp_problems: 1 },
  };
}

export function businessDetail(overrides: Partial<BusinessDetail> = {}): BusinessDetail {
  return {
    ...businessRow({ whatsapp: "action_required", needs_help: true }),
    suspended_reason: null,
    suspended_at: null,
    onboarding: [
      { key: "account", done: true },
      { key: "agent_configured", done: true },
      { key: "agent_tested", done: true },
      { key: "whatsapp_connected", done: false },
      { key: "own_properties", done: false },
    ],
    whatsapp_connection: {
      status: "error",
      display_phone_number: "+54 9 11 5555-0100",
      verified_name: "Inmo Sur",
      last_inbound_at: "2026-11-04T10:00:00Z",
      connected_at: "2026-10-27T12:00:00Z",
      quality_rating: "GREEN",
      business_verification: "pending",
      failing_since: "2026-11-04T08:00:00Z",
      error: {
        code: "token_revoked",
        title: "El permiso de Meta venció",
        message: "Tu agente no puede responder.",
        action: "Volvé a conectar.",
      },
      signup_step: null,
      signup_error: null,
      phone_number_id: null,
      waba_id: null,
      business_id: "biz-1",
      sender: "cloud",
      template_name: "hello_world",
      template_language: "en_US",
      visit_template_name: null,
      visit_template_language: "es_AR",
      last_error_code: "190",
      admin_error: {
        code: "token_revoked",
        title: "El permiso de Meta venció",
        message: "Tu agente no puede responder.",
        action: "Volvé a conectar.",
        meta_code: "190",
        admin_detail: "El cliente quitó el acceso de la app en su cuenta de Meta.",
      },
      updated_at: "2026-11-04T08:00:00Z",
      has_access_token: true,
      waba_masked: "•••• 4321",
    },
    usage: { conversations_this_month: 1234, allowance: 1000, users: 2 },
    users: [
      { id: "u1", name: "Ana", email: "duena@sur.test", role: "owner" },
      { id: "u2", name: "vendedor@sur.test", email: "vendedor@sur.test", role: "agent" },
    ],
    activity: [
      {
        at: "2026-11-04T08:00:00Z",
        actor_kind: "system",
        actor_name: null,
        action: "whatsapp_error",
        details: { meta_code: "190" },
      },
      {
        at: "2026-10-27T12:00:00Z",
        actor_kind: "user",
        actor_name: "Ana",
        action: "properties_imported",
        details: { created: 12, updated: 0, failed: 2 },
      },
    ],
    ...overrides,
  };
}

export function systemHealth(overrides: Partial<SystemHealth> = {}): SystemHealth {
  return {
    jobs: [
      { kind: "whatsapp.send", status: "queued", count: 3 },
      { kind: "lead.email_handoff", status: "dead", count: 1 },
    ],
    dead_last_24h: 1,
    oldest_queued_seconds: 95,
    webhooks_last_hour: 42,
    signature_rejections_last_24h: 2,
    failed_sends_last_24h: [{ code: "131026", count: 4 }],
    version: "0.7.0",
    commit: "abc1234",
    database: "ok",
    ...overrides,
  };
}
