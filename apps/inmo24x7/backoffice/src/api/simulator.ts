import {
  ApiRequestError,
  errorCode,
  type SimulatorReply,
  type SimulatorState,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

const params = (tenantId: string) => ({ params: { path: { tenant_id: tenantId } } });

export async function fetchTenantSimulator(tenantId: string): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}/simulator",
    params(tenantId),
  );
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function sendTenantSimulatorMessage(
  tenantId: string,
  text: string,
): Promise<SimulatorReply> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/simulator/messages",
    { ...params(tenantId), body: { text } },
  );
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function resetTenantSimulator(tenantId: string): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/simulator/reset",
    params(tenantId),
  );
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
