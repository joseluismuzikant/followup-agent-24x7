import { ApiRequestError, errorCode } from "@followup/api-client-inmo24x7";
import type { LeadDetail, LeadList, LeadStatus } from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export interface LeadFilters {
  status?: LeadStatus;
  includeTest?: boolean;
  page?: number;
}

export async function fetchLeads(filters: LeadFilters = {}): Promise<LeadList> {
  const { data, error, response } = await apiClient.GET("/leads", {
    params: {
      query: {
        status: filters.status,
        include_test: filters.includeTest ?? false,
        page: filters.page ?? 1,
      },
    },
  });
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function fetchLead(id: string): Promise<LeadDetail> {
  const { data, error, response } = await apiClient.GET("/leads/{lead_id}", {
    params: { path: { lead_id: id } },
  });
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
