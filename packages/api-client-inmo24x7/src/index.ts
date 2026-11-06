import { createApiClient as createSharedClient } from "@followup/app-shell/api";
import type { ApiClientOptions } from "@followup/app-shell/api";

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
export type BusinessCreated = components["schemas"]["BusinessCreatedRead"];
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

// The shared client (bearer token, 5xx hook, request id) lives in @followup/app-shell/api;
// this package adds inmo24x7's generated types.
export {
  ApiRequestError,
  REQUEST_ID_HEADER,
  apiError,
  errorCode,
  serverErrorInfo,
  type ApiClientOptions,
  type ServerErrorInfo,
} from "@followup/app-shell/api";

export function createApiClient(baseUrl: string, options: ApiClientOptions = {}) {
  return createSharedClient<paths>(baseUrl, options);
}

export type ApiClient = ReturnType<typeof createApiClient>;
