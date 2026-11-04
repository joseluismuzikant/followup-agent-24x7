import type {
  BusinessUsage,
  ErrorList,
  SentryIssue,
  TenantUsage,
  UsageFigures,
  UsageReport,
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
    links: { grafana_url: "", loki_datasource: "", sentry_issues_url: "" },
    ...overrides,
  };
}

export function sentryIssue(overrides: Partial<SentryIssue> = {}): SentryIssue {
  return {
    id: "101",
    title: "RuntimeError: boom",
    culprit: "inmo24x7_api.leads.router in get_lead",
    project: "api",
    first_seen: "2026-11-01T10:00:00Z",
    last_seen: "2026-11-04T12:00:00Z",
    count: 12,
    users: 3,
    permalink: "https://acme.sentry.io/issues/101/",
    ...overrides,
  };
}

export function errorList(overrides: Partial<ErrorList> = {}): ErrorList {
  return {
    configured: true,
    available: true,
    issues: [sentryIssue(), sentryIssue({ id: "102", title: "TypeError: x", project: "panel" })],
    sentry_issues_url: "https://acme.sentry.io/issues/",
    ...overrides,
  };
}

export function usageFigures(overrides: Partial<UsageFigures> = {}): UsageFigures {
  return {
    llm_calls: 40,
    input_tokens: 120_000,
    output_tokens: 9_000,
    cost_usd: "0.493000",
    cost_per_conversation_usd: "0.049300",
    test_share: 0.25,
    conversations: 10,
    template_messages: 3,
    unpriced_calls: 0,
    unreported_calls: 0,
    ...overrides,
  };
}

export function businessUsage(overrides: Partial<BusinessUsage> = {}): BusinessUsage {
  return {
    tenant_id: "tenant-1",
    name: "Inmobiliaria Sur",
    plan: "trial",
    figures: usageFigures(),
    ...overrides,
  };
}

export function usageReport(overrides: Partial<UsageReport> = {}): UsageReport {
  return {
    month: "2026-11",
    totals: usageFigures({ cost_usd: "0.593000", conversations: 12 }),
    businesses: [
      businessUsage(),
      businessUsage({
        tenant_id: "tenant-2",
        name: "Inmobiliaria Norte",
        figures: usageFigures({ cost_usd: "0.100000", unpriced_calls: 4, conversations: 2 }),
      }),
    ],
    ...overrides,
  };
}

export function tenantUsage(overrides: Partial<TenantUsage> = {}): TenantUsage {
  return {
    month: "2026-11",
    business: businessUsage(),
    daily: [
      { day: "2026-11-01", cost_usd: "0.100000", conversations: 2 },
      { day: "2026-11-02", cost_usd: "0.393000", conversations: 8 },
      { day: "2026-11-03", cost_usd: "0.000000", conversations: 0 },
    ],
    by_operation: [
      { key: "compose_reply", llm_calls: 20, input_tokens: 80_000, output_tokens: 8_000, cost_usd: "0.360000", unpriced_calls: 0 },
      { key: "extract", llm_calls: 20, input_tokens: 40_000, output_tokens: 1_000, cost_usd: "0.133000", unpriced_calls: 0 },
    ],
    by_model: [
      { key: "anthropic:claude-sonnet-5-5", llm_calls: 40, input_tokens: 120_000, output_tokens: 9_000, cost_usd: "0.493000", unpriced_calls: 0 },
    ],
    ...overrides,
  };
}
