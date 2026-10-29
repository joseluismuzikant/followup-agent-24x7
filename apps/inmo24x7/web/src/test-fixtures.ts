import type {
  AgentConfig,
  AgentSetup,
  MeResponse,
  OnboardingState,
} from "@followup/api-client-inmo24x7";

export const defaultConfig: AgentConfig = {
  agent_name: "Sofía",
  tone: "warm",
  after_hours_mode: "keep_answering_and_propose_visit",
  qualification_questions: [
    { key: "operation", label: "Si busca comprar o alquilar", kind: "choice", options: ["compra", "alquiler"], enabled: true },
    { key: "zone", label: "Zona o barrio", kind: "text", options: [], enabled: true },
    { key: "budget", label: "Presupuesto", kind: "money", options: [], enabled: true },
  ],
};

const weekdays = [0, 1, 2, 3, 4].map((weekday) => ({
  weekday,
  opens: "09:00",
  closes: "18:00",
}));

export function agentSetup(overrides: Partial<AgentSetup> = {}): AgentSetup {
  return {
    config: defaultConfig,
    version: 0,
    updated_at: null,
    business_hours: weekdays,
    notification_emails: ["duena@example.com"],
    defaults: defaultConfig,
    ...overrides,
  };
}

export function onboardingState(
  currentStep: string,
  overrides: Partial<OnboardingState> = {},
): OnboardingState {
  const order = ["business", "agent", "try", "whatsapp", "done"];
  return {
    current_step: currentStep,
    completed_steps: order
      .slice(0, order.indexOf(currentStep))
      .map((step) => ({ step, completed_at: "2026-10-28T12:00:00Z" })),
    finished: currentStep === "done",
    checklist: {
      items: [
        { key: "account", done: true },
        { key: "agent", done: false },
        { key: "whatsapp", done: false },
        { key: "properties", done: false },
        { key: "meta", done: false },
      ],
      ready_count: 1,
      total: 5,
      facts: {
        account_created: true,
        agent_configured: false,
        agent_tested: false,
        whatsapp_connected: false,
        own_properties: false,
        meta_business_verified: false,
      },
    },
    ...overrides,
  };
}

export function me(role = "owner"): MeResponse {
  return {
    profile: {
      id: "11111111-1111-1111-1111-111111111111",
      email: "duena@example.com",
      display_name: "duena@example.com",
      tenant_id: "22222222-2222-2222-2222-222222222222",
      role,
      is_platform_admin: false,
    },
    tenant: {
      id: "22222222-2222-2222-2222-222222222222",
      name: "Inmobiliaria Sur",
      slug: "inmobiliaria-sur",
      status: "active",
      trial_ends_at: "2099-01-01T00:00:00Z",
      created_at: "2026-10-28T12:00:00Z",
    },
  };
}
