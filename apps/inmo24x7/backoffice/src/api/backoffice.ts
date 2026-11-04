import { ApiRequestError, errorCode } from "@followup/api-client-inmo24x7";
import type {
  BusinessCreateInput,
  BusinessDetail,
  BusinessFilter,
  BusinessList,
  PlanSummary,
  SystemHealth,
  WhatsAppConnection,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";
import { WhatsAppRequestError } from "./whatsapp";

function fail(status: number, error: unknown): never {
  throw new ApiRequestError(status, errorCode(error));
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
  return data ?? fail(response.status, error);
}

export async function createBusiness(input: BusinessCreateInput): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST("/admin/tenants", { body: input });
  return data ?? fail(response.status, error);
}

export async function fetchBusiness(tenantId: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}",
    tenantPath(tenantId),
  );
  return data ?? fail(response.status, error);
}

export async function suspendBusiness(tenantId: string, reason: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST("/admin/tenants/{tenant_id}/suspend", {
    ...tenantPath(tenantId),
    body: { reason },
  });
  return data ?? fail(response.status, error);
}

export async function reactivateBusiness(tenantId: string): Promise<BusinessDetail> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/reactivate",
    tenantPath(tenantId),
  );
  return data ?? fail(response.status, error);
}

export async function sendReconnectLink(tenantId: string): Promise<number> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/whatsapp/reconnect-link",
    tenantPath(tenantId),
  );
  return data?.recipients ?? fail(response.status, error);
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
  return data ?? fail(response.status, error);
}

export async function fetchPlans(): Promise<PlanSummary[]> {
  const { data, error, response } = await apiClient.GET("/admin/plans");
  return data ?? fail(response.status, error);
}
