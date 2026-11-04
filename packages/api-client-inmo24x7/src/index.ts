import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type LivenessResponse = components["schemas"]["LivenessResponse"];
export type ReadinessResponse = components["schemas"]["ReadinessResponse"];
export type Tenant = components["schemas"]["TenantRead"];
export type TenantPage = components["schemas"]["TenantPageRead"];
export type TenantSummary = components["schemas"]["TenantSummaryRead"];
export type Profile = components["schemas"]["ProfileRead"];
export type MeResponse = components["schemas"]["MeResponse"];
export type SignUpResponse = components["schemas"]["SignUpResponse"];
export type OnboardingState = components["schemas"]["OnboardingRead"];
export type SetupChecklist = components["schemas"]["ChecklistRead"];
export type AgentSetup = components["schemas"]["AgentSetupRead"];
export type AgentSetupInput = components["schemas"]["AgentSetupWrite"];
export type AgentConfig = components["schemas"]["AgentConfigModel"];
export type AgentQuestion = components["schemas"]["QuestionModel"];
export type AgentConfigInput = components["schemas"]["AgentConfigInputModel"];
export type AgentQuestionInput = components["schemas"]["QuestionInputModel"];
export type ScheduleBlock = components["schemas"]["ScheduleBlockModel"];
export type AgentVersion = components["schemas"]["AgentVersionRead"];
export type SimulatorState = components["schemas"]["SimulatorRead"];
export type SimulatorReply = components["schemas"]["SimulatorReplyRead"];
export type SimulatorMessage = components["schemas"]["MessageRead"];
export type SimulatorPropertyCard = components["schemas"]["PropertyCardRead"];
export type SimulatorSlot = components["schemas"]["SlotRead"];
export type KnownFactRow = components["schemas"]["KnownFactRead"];
export type TenantSettings = components["schemas"]["TenantSettingsRead"];
export type TenantSettingsInput = components["schemas"]["TenantSettingsWrite"];
export type Property = components["schemas"]["PropertyRead"];
export type PropertyList = components["schemas"]["PropertyListRead"];
export type PropertyInput = components["schemas"]["PropertyCreate"];
export type PropertyChanges = components["schemas"]["PropertyUpdate"];
export type ImportReport = components["schemas"]["ImportReportRead"];
export type Lead = components["schemas"]["LeadRead"];
export type LeadList = components["schemas"]["LeadListRead"];
export type LeadDetail = components["schemas"]["LeadDetailRead"];
export type LeadStatus = Lead["status"];
export type LeadVisit = components["schemas"]["VisitRead"];
export type LeadTabCounts = components["schemas"]["TabCountsRead"];
export type LeadControl = components["schemas"]["ControlRead"];
export type ServiceWindow = components["schemas"]["ServiceWindowRead"];
export type InboxTab = "attention" | "visits" | "all";
export type Dashboard = components["schemas"]["DashboardRead"];
export type DashboardLead = components["schemas"]["TodayLeadRead"];
export type DeliveryStatus = NonNullable<SimulatorMessage["delivery_status"]>;
export type WhatsAppStatus = components["schemas"]["WhatsAppStatusRead"];
export type WhatsAppConnection = components["schemas"]["WhatsAppConnectionRead"];
export type WhatsAppConnectionInput = components["schemas"]["WhatsAppConnectionWrite"];
export type WhatsAppError = components["schemas"]["WhatsAppErrorRead"];
export type EmbeddedSignupInput = components["schemas"]["EmbeddedSignupWrite"];
export type SignupAbandonedInput = components["schemas"]["SignupAbandonedWrite"];
export type BusinessList = components["schemas"]["BusinessListRead"];
export type BusinessRow = components["schemas"]["BusinessRowRead"];
export type BusinessDetail = components["schemas"]["BusinessDetailRead"];
export type BusinessCreateInput = components["schemas"]["BusinessCreate"];
export type BusinessActivity = components["schemas"]["ActivityRead"];
export type BusinessFilter = "all" | "needs_help" | "trial";
export type SystemHealth = components["schemas"]["SystemRead"];
export type PlanSummary = components["schemas"]["PlanSummaryRead"];

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(`API request failed (${status}): ${code}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

export function errorCode(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
  ) {
    return error.code;
  }
  return "unknown_error";
}

export interface ApiClientOptions {
  getAccessToken?: () => string | null | undefined | Promise<string | null | undefined>;
}

export function createApiClient(baseUrl: string, options: ApiClientOptions = {}) {
  return createClient<paths>({
    baseUrl: baseUrl.replace(/\/$/, ""),
    fetch: async (request) => {
      const token = await options.getAccessToken?.();
      if (!token) {
        return globalThis.fetch(request);
      }
      const headers = new Headers(request.headers);
      headers.set("Authorization", `Bearer ${token}`);
      return globalThis.fetch(new Request(request, { headers }));
    },
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;
