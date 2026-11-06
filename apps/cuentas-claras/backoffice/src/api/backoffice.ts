import { apiError } from "@followup/api-client-cuentas-claras";
import type {
  BusinessCreated,
  BusinessCreateInput,
  BusinessDetail,
  BusinessList,
} from "@followup/api-client-cuentas-claras";

import { apiClient } from "./client";

function fail(response: Response, error: unknown): never {
  throw apiError(response, error);
}

const tenantPath = (tenantId: string) => ({ params: { path: { tenant_id: tenantId } } });

export async function fetchBusinesses(q: string, page: number): Promise<BusinessList> {
  const { data, error, response } = await apiClient.GET("/admin/tenants", {
    params: { query: { q, page } },
  });
  return data ?? fail(response, error);
}

export async function createBusiness(input: BusinessCreateInput): Promise<BusinessCreated> {
  const { data, error, response } = await apiClient.POST("/admin/tenants", { body: input });
  return data ?? fail(response, error);
}

export async function resendInvitation(tenantId: string): Promise<{ sent: boolean }> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/invitation",
    tenantPath(tenantId),
  );
  return data ?? fail(response, error);
}

export async function resetTemporaryPassword(
  tenantId: string,
): Promise<{ temporary_password: string }> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/temporary-password",
    tenantPath(tenantId),
  );
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
