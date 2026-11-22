import { apiError, ApiRequestError } from "@followup/api-client-inmo24x7";
import type {
  ConditionSettings,
  ConditionSettingsInput,
  ImportReport,
  ListingDraft,
  ListingRefresh,
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

export async function fetchConditionSettings(): Promise<ConditionSettings> {
  const { data, error, response } = await apiClient.GET("/condition-settings");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Condiciones generales": the agency's defaults and Sofía's behavior. */
export async function saveConditionSettings(
  input: ConditionSettingsInput,
): Promise<ConditionSettings> {
  const { data, error, response } = await apiClient.PUT("/condition-settings", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Cargar desde un link": the publication read into a draft (nothing is saved). */
export async function readListingLink(url: string): Promise<ListingDraft> {
  const { data, error, response } = await apiClient.POST("/properties/from-link", {
    body: { url },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Pegar texto de la publicación", for portals that do not let us read the link. */
export async function readListingText(text: string, link: string): Promise<ListingDraft> {
  const { data, error, response } = await apiClient.POST("/properties/from-text", {
    body: { text, link },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Actualizar desde el link": what the publication says now, as changes to apply. */
export async function refreshFromLink(id: string, text?: string): Promise<ListingRefresh> {
  const { data, error, response } = await apiClient.POST(
    "/properties/{property_id}/refresh-from-link",
    { params: { path: { property_id: id } }, body: { text: text ?? null } },
  );
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
