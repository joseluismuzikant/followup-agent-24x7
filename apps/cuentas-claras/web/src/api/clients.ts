import {
  apiError,
  type ClientDetail,
  type ClientInput,
  type ClientList,
  type ClientUpdateInput,
} from "@followup/api-client-cuentas-claras";

import { apiClient } from "./client";

export interface ClientFilters {
  q?: string;
  missingWhatsapp?: boolean;
  page?: number;
}

export async function fetchClients(filters: ClientFilters = {}): Promise<ClientList> {
  const { data, error, response } = await apiClient.GET("/clients", {
    params: {
      query: {
        q: filters.q || undefined,
        missing_whatsapp: filters.missingWhatsapp || undefined,
        page: filters.page,
      },
    },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchClient(id: string): Promise<ClientDetail> {
  const { data, error, response } = await apiClient.GET("/clients/{client_id}", {
    params: { path: { client_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function createClient(input: ClientInput): Promise<ClientDetail> {
  const { data, error, response } = await apiClient.POST("/clients", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function updateClient(id: string, input: ClientUpdateInput): Promise<ClientDetail> {
  const { data, error, response } = await apiClient.PATCH("/clients/{client_id}", {
    params: { path: { client_id: id } },
    body: input,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
