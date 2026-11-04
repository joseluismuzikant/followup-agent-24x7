import { ApiRequestError, errorCode, REQUEST_ID_HEADER } from "@followup/api-client-inmo24x7";
import type {
  WhatsAppConnection,
  WhatsAppConnectionInput,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

/** A failed call with Meta's error code (admins see it). */
export class WhatsAppRequestError extends ApiRequestError {
  readonly metaCode: string | null;

  constructor(status: number, code: string, metaCode: string | null, requestId: string | null = null) {
    super(status, code, requestId);
    this.metaCode = metaCode;
  }
}

function failure(response: Response, error: unknown): WhatsAppRequestError {
  const metaCode =
    typeof error === "object" && error !== null && "meta_code" in error
      ? String(error.meta_code)
      : null;
  return new WhatsAppRequestError(
    response.status,
    errorCode(error),
    metaCode,
    response.headers.get(REQUEST_ID_HEADER),
  );
}

const path = (tenantId: string) => ({ params: { path: { tenant_id: tenantId } } });

export async function fetchConnection(tenantId: string): Promise<WhatsAppConnection> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}/whatsapp",
    path(tenantId),
  );
  if (data) {
    return data;
  }
  throw failure(response, error);
}

export async function saveConnection(
  tenantId: string,
  input: WhatsAppConnectionInput,
): Promise<WhatsAppConnection> {
  const { data, error, response } = await apiClient.PUT("/admin/tenants/{tenant_id}/whatsapp", {
    ...path(tenantId),
    body: input,
  });
  if (data) {
    return data;
  }
  throw failure(response, error);
}

export type ConnectionAction = "test" | "subscribe" | "disconnect";

export async function runConnectionAction(
  tenantId: string,
  action: ConnectionAction,
): Promise<WhatsAppConnection> {
  const routes = {
    test: "/admin/tenants/{tenant_id}/whatsapp/test",
    subscribe: "/admin/tenants/{tenant_id}/whatsapp/subscribe",
    disconnect: "/admin/tenants/{tenant_id}/whatsapp/disconnect",
  } as const;
  const { data, error, response } = await apiClient.POST(routes[action], path(tenantId));
  if (data && "status" in data) {
    return data;
  }
  throw failure(response, error);
}

export async function sendTestMessage(tenantId: string, to: string): Promise<string> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/whatsapp/test-message",
    { ...path(tenantId), body: { to } },
  );
  if (data && "wamid" in data) {
    return data.wamid;
  }
  throw failure(response, error);
}
