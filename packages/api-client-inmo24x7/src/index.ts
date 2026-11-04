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
export type MonitoringLinks = components["schemas"]["MonitoringLinksRead"];
export type ErrorList = components["schemas"]["ErrorsRead"];
export type SentryIssue = components["schemas"]["IssueRead"];
export type UsageReport = components["schemas"]["UsageReportRead"];
export type UsageFigures = components["schemas"]["UsageFiguresRead"];
export type BusinessUsage = components["schemas"]["BusinessUsageRead"];
export type TenantUsage = components["schemas"]["TenantUsageRead"];
export type DailyUsage = components["schemas"]["DailyUsageRead"];
export type UsageSplit = components["schemas"]["UsageSplitRead"];

export const REQUEST_ID_HEADER = "X-Request-ID";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  /** The API's X-Request-ID: the "código de referencia" a customer can report. */
  readonly requestId: string | null;

  constructor(status: number, code: string, requestId: string | null = null) {
    super(`API request failed (${status}): ${code}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }

  /** What the panels show as "Código de referencia": the first 8 characters. */
  get reference(): string | null {
    return this.requestId ? this.requestId.slice(0, 8) : null;
  }
}

/** The error for a failed response, with its code and request id. */
export function apiError(response: Response, body: unknown): ApiRequestError {
  return new ApiRequestError(
    response.status,
    errorCode(body),
    response.headers.get(REQUEST_ID_HEADER),
  );
}

/** What the panels report about a 5xx: never bodies or query strings. */
export interface ServerErrorInfo {
  status: number;
  method: string;
  path: string;
  requestId: string | null;
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
  /** Called for every 5xx answer (the panels send it to Sentry). */
  onServerError?: (info: ServerErrorInfo) => void;
}

export function serverErrorInfo(request: Request, response: Response): ServerErrorInfo {
  return {
    status: response.status,
    method: request.method,
    path: new URL(request.url).pathname,
    requestId: response.headers.get(REQUEST_ID_HEADER),
  };
}

export function createApiClient(baseUrl: string, options: ApiClientOptions = {}) {
  return createClient<paths>({
    baseUrl: baseUrl.replace(/\/$/, ""),
    fetch: async (request) => {
      const token = await options.getAccessToken?.();
      let outgoing = request;
      if (token) {
        const headers = new Headers(request.headers);
        headers.set("Authorization", `Bearer ${token}`);
        outgoing = new Request(request, { headers });
      }
      const response = await globalThis.fetch(outgoing);
      if (response.status >= 500) {
        options.onServerError?.(serverErrorInfo(outgoing, response));
      }
      return response;
    },
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;
