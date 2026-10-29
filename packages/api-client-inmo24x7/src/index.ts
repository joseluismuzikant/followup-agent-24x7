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
export type TenantSettings = components["schemas"]["TenantSettingsRead"];
export type TenantSettingsInput = components["schemas"]["TenantSettingsWrite"];

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
