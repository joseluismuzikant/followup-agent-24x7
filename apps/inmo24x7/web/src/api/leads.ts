import { apiError, ApiRequestError, REQUEST_ID_HEADER } from "@followup/api-client-inmo24x7";
import type {
  InboxTab,
  LeadDetail,
  LeadList,
  SimulatorMessage,
} from "@followup/api-client-inmo24x7";

import { apiClient, authorizedFetch } from "./client";

export interface LeadFilters {
  tab?: InboxTab;
  q?: string;
  includeTest?: boolean;
  page?: number;
}

function leadQuery(filters: LeadFilters) {
  return {
    tab: filters.tab ?? "all",
    q: filters.q?.trim() || undefined,
    include_test: filters.includeTest ?? false,
  };
}

export async function fetchLeads(filters: LeadFilters = {}): Promise<LeadList> {
  const { data, error, response } = await apiClient.GET("/leads", {
    params: { query: { ...leadQuery(filters), page: filters.page ?? 1 } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchLead(id: string): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.GET("/leads/{lead_id}", {
    params: { path: { lead_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function takeOverLead(id: string): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.POST("/leads/{lead_id}/takeover", {
    params: { path: { lead_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function releaseLead(id: string): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.POST("/leads/{lead_id}/release", {
    params: { path: { lead_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function sendTeamMessage(id: string, text: string): Promise<SimulatorMessage> {
  const { data, error, response } = await apiClient.POST("/leads/{lead_id}/messages", {
    params: { path: { lead_id: id } },
    body: { text },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function confirmVisit(
  leadId: string,
  visitId: string,
  startsAt?: string,
): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.POST(
    "/leads/{lead_id}/visits/{visit_id}/confirm",
    {
      params: { path: { lead_id: leadId, visit_id: visitId } },
      body: { starts_at: startsAt ?? null },
    },
  );
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function cancelVisit(
  leadId: string,
  visitId: string,
  message?: string,
): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.POST(
    "/leads/{lead_id}/visits/{visit_id}/cancel",
    {
      params: { path: { lead_id: leadId, visit_id: visitId } },
      body: { message: message?.trim() || null },
    },
  );
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Exportar CSV": the file needs the session token, so it is fetched and saved as a blob. */
export async function downloadLeadsCsv(filters: LeadFilters): Promise<void> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(leadQuery(filters))) {
    if (value !== undefined) {
      query.set(key, String(value));
    }
  }
  const response = await authorizedFetch(`/leads/export.csv?${query.toString()}`);
  if (!response.ok) {
    throw new ApiRequestError(response.status, "export_failed", response.headers.get(REQUEST_ID_HEADER));
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "consultas.csv";
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
