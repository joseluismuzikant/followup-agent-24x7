import { apiError, errorCode } from "@followup/api-client-inmo24x7";
import type {
  ErrorList,
  TenantUsage,
  UsageReport,
  BusinessCreateInput,
  BusinessDetail,
  BusinessFilter,
  BusinessList,
  PlanSummary,
  SystemHealth,
  WhatsAppConnection,
} from "@followup/api-client-inmo24x7";

import { apiClient, authorizedFetch } from "./client";
import { WhatsAppRequestError } from "./whatsapp";

function fail(response: Response, error: unknown): never {
  throw apiError(response, error);
}

const tenantPath = (tenantId: string) => ({ params: { path: { tenant_id: tenantId } } });

export async function fetchBusinesses(
  filter: BusinessFilter,
  q: string,
  page: number,
): Promise<BusinessList> {
  const { data, error, response } = await apiClient.GET("/admin/tenants", {
    params: { query: { filter, q, page } },
  });
  return data ?? fail(response, error);
}

export async function createBusiness(input: BusinessCreateInput): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST("/admin/tenants", { body: input });
  return data ?? fail(response, error);
}

export async function fetchBusiness(tenantId: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}",
    tenantPath(tenantId),
  );
  return data ?? fail(response, error);
}

export async function suspendBusiness(tenantId: string, reason: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST("/admin/tenants/{tenant_id}/suspend", {
    ...tenantPath(tenantId),
    body: { reason },
  });
  return data ?? fail(response, error);
}

export async function reactivateBusiness(tenantId: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/reactivate",
    tenantPath(tenantId),
  );
  return data ?? fail(response, error);
}

export async function sendReconnectLink(tenantId: string): Promise<number> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/whatsapp/reconnect-link",
    tenantPath(tenantId),
  );
  return data?.recipients ?? fail(response, error);
}

export async function retrySignup(tenantId: string): Promise<WhatsAppConnection> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/whatsapp/retry-signup",
    tenantPath(tenantId),
  );
  if (data) {
    return data;
  }
  const metaCode =
    typeof error === "object" && error !== null && "meta_code" in error
      ? String(error.meta_code)
      : null;
  throw new WhatsAppRequestError(response.status, errorCode(error), metaCode);
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const { data, error, response } = await apiClient.GET("/admin/system");
  return data ?? fail(response, error);
}

export async function fetchPlans(): Promise<PlanSummary[]> {
  const { data, error, response } = await apiClient.GET("/admin/plans");
  return data ?? fail(response, error);
}

export type ErrorProject = "all" | "api" | "panel" | "backoffice";
export type ErrorPeriod = "24h" | "7d" | "14d";

export interface ErrorFilters {
  project?: ErrorProject;
  period?: ErrorPeriod;
  tenantId?: string;
  limit?: number;
}

/** Open Sentry issues; `configured` / `available` say why the list may be empty. */
export async function fetchErrors(filters: ErrorFilters = {}): Promise<ErrorList> {
  const { data, error, response } = await apiClient.GET("/admin/errors", {
    params: {
      query: {
        project: filters.project ?? "all",
        period: filters.period ?? "24h",
        tenant_id: filters.tenantId,
        limit: filters.limit ?? 25,
      },
    },
  });
  return data ?? fail(response, error);
}

/** Consumo of one UTC month ("2026-11"); the current month when omitted. */
export async function fetchUsage(month?: string): Promise<UsageReport> {
  const { data, error, response } = await apiClient.GET("/admin/usage", {
    params: { query: { month } },
  });
  return data ?? fail(response, error);
}

export async function fetchTenantUsage(tenantId: string, month?: string): Promise<TenantUsage> {
  const { data, error, response } = await apiClient.GET("/admin/usage/{tenant_id}", {
    params: { path: { tenant_id: tenantId }, query: { month } },
  });
  return data ?? fail(response, error);
}

export async function downloadUsageCsv(month: string): Promise<void> {
  const response = await authorizedFetch(`/admin/usage/export.csv?month=${month}`);
  if (!response.ok) {
    throw apiError(response, await response.json().catch(() => null));
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `consumo-${month}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** Makes the API fail on purpose (500) so Sentry gets a test issue. Resolves with the
 * reference code of that request. */
export async function triggerApiTestError(): Promise<string | null> {
  const { response } = await apiClient.POST("/admin/errors/test");
  if (response.status !== 500) {
    throw apiError(response, null);
  }
  return response.headers.get("X-Request-ID")?.slice(0, 8) ?? null;
}
