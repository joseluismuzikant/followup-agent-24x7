import { apiError } from "@followup/api-client-cuentas-claras";
import type {
  AdminReminders,
  PlanResult,
  WhatsAppConnection,
  WhatsAppConnectionInput,
} from "@followup/api-client-cuentas-claras";
import { connectionFailure } from "@followup/app-shell";
import type { ConnectionAction, WhatsAppAdminApi } from "@followup/app-shell";

import { apiClient } from "./client";

const tenantPath = (tenantId: string) => ({ params: { path: { tenant_id: tenantId } } });

/** Template statuses, the last reminder errors and this month's count (C5, Day 9). */
export async function fetchAdminReminders(tenantId: string): Promise<AdminReminders> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}/reminders",
    tenantPath(tenantId),
  );
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Planificar ahora": the business's planner runs right away. */
export async function planReminders(tenantId: string): Promise<PlanResult> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/reminders/plan",
    tenantPath(tenantId),
  );
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Actualizar estados": asks Meta for the templates' status (a job). */
export async function syncTemplates(tenantId: string): Promise<void> {
  const { error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/reminders/templates/sync",
    tenantPath(tenantId),
  );
  if (!response.ok) {
    throw apiError(response, error);
  }
}

async function fetchConnection(tenantId: string): Promise<WhatsAppConnection> {
  const { data, error, response } = await apiClient.GET(
    "/admin/tenants/{tenant_id}/whatsapp",
    tenantPath(tenantId),
  );
  if (data) {
    return data;
  }
  throw connectionFailure(response, error);
}

async function saveConnection(
  tenantId: string,
  input: WhatsAppConnectionInput,
): Promise<WhatsAppConnection> {
  const { data, error, response } = await apiClient.PUT("/admin/tenants/{tenant_id}/whatsapp", {
    ...tenantPath(tenantId),
    body: input,
  });
  if (data) {
    return data;
  }
  throw connectionFailure(response, error);
}

async function runConnectionAction(
  tenantId: string,
  action: ConnectionAction,
): Promise<WhatsAppConnection> {
  const routes = {
    test: "/admin/tenants/{tenant_id}/whatsapp/test",
    subscribe: "/admin/tenants/{tenant_id}/whatsapp/subscribe",
    disconnect: "/admin/tenants/{tenant_id}/whatsapp/disconnect",
  } as const;
  const { data, error, response } = await apiClient.POST(routes[action], tenantPath(tenantId));
  if (data && "status" in data) {
    return data;
  }
  throw connectionFailure(response, error);
}

async function sendTestMessage(tenantId: string, to: string): Promise<string> {
  const { data, error, response } = await apiClient.POST(
    "/admin/tenants/{tenant_id}/whatsapp/test-message",
    { ...tenantPath(tenantId), body: { to } },
  );
  if (data && "wamid" in data) {
    return data.wamid;
  }
  throw connectionFailure(response, error);
}

export const whatsappAdminApi: WhatsAppAdminApi = {
  fetchConnection,
  saveConnection,
  runConnectionAction,
  sendTestMessage,
};
