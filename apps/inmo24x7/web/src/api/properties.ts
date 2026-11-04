import { apiError, ApiRequestError } from "@followup/api-client-inmo24x7";
import type {
  ImportReport,
  Property,
  PropertyChanges,
  PropertyInput,
  PropertyList,
} from "@followup/api-client-inmo24x7";

import { apiClient, authorizedFetch } from "./client";

export interface PropertyFilters {
  search?: string;
  operation?: "sale" | "rent";
  page?: number;
}

export async function fetchProperties(filters: PropertyFilters = {}): Promise<PropertyList> {
  const { data, error, response } = await apiClient.GET("/properties", {
    params: {
      query: {
        search: filters.search || undefined,
        operation: filters.operation,
        page: filters.page ?? 1,
      },
    },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function createProperty(input: PropertyInput): Promise<Property> {
  const { data, error, response } = await apiClient.POST("/properties", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function updateProperty(id: string, changes: PropertyChanges): Promise<Property> {
  const { data, error, response } = await apiClient.PATCH("/properties/{property_id}", {
    params: { path: { property_id: id } },
    body: changes,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function setPropertyPublished(id: string, published: boolean): Promise<Property> {
  const path = published ? "/properties/{property_id}/publish" : "/properties/{property_id}/pause";
  const { data, error, response } = await apiClient.POST(path, {
    params: { path: { property_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

async function failure(response: Response): Promise<ApiRequestError> {
  const body: unknown = await response.json().catch(() => null);
  return apiError(response, body);
}

export async function importProperties(file: File): Promise<ImportReport> {
  const body = new FormData();
  body.append("file", file, file.name);
  const response = await authorizedFetch("/properties/import", { method: "POST", body });
  if (!response.ok) {
    throw await failure(response);
  }
  return (await response.json()) as ImportReport;
}

async function download(path: string, fileName: string): Promise<void> {
  const response = await authorizedFetch(path);
  if (!response.ok) {
    throw await failure(response);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadImportErrors(importId: string): Promise<void> {
  return download(`/properties/import/${importId}/errors.csv`, "propiedades-con-errores.csv");
}

export function downloadImportTemplate(): Promise<void> {
  return download("/properties/import-template.csv", "plantilla-propiedades.csv");
}
