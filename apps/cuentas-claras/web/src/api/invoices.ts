import {
  apiError,
  type ImportReport,
  type InvoiceDetail,
  type InvoiceInput,
  type InvoiceList,
  type InvoiceTab,
  type MarkPaidInput,
  type Summary,
} from "@followup/api-client-cuentas-claras";

import { apiClient, authorizedFetch } from "./client";
import { download, failure } from "./files";

export interface InvoiceFilters {
  tab?: InvoiceTab;
  q?: string;
  page?: number;
}

export async function fetchInvoices(filters: InvoiceFilters = {}): Promise<InvoiceList> {
  const { data, error, response } = await apiClient.GET("/invoices", {
    params: { query: { tab: filters.tab, q: filters.q || undefined, page: filters.page } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchInvoice(id: string): Promise<InvoiceDetail> {
  const { data, error, response } = await apiClient.GET("/invoices/{invoice_id}", {
    params: { path: { invoice_id: id } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function createInvoice(input: InvoiceInput): Promise<InvoiceDetail> {
  const { data, error, response } = await apiClient.POST("/invoices", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function updateInvoice(id: string, input: InvoiceInput): Promise<InvoiceDetail> {
  const { data, error, response } = await apiClient.PATCH("/invoices/{invoice_id}", {
    params: { path: { invoice_id: id } },
    body: input,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function markInvoicePaid(id: string, input: MarkPaidInput): Promise<InvoiceDetail> {
  const { data, error, response } = await apiClient.POST("/invoices/{invoice_id}/mark-paid", {
    params: { path: { invoice_id: id } },
    body: input,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function cancelInvoice(id: string, reason: string): Promise<InvoiceDetail> {
  const { data, error, response } = await apiClient.POST("/invoices/{invoice_id}/cancel", {
    params: { path: { invoice_id: id } },
    body: { reason },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchSummary(): Promise<Summary> {
  const { data, error, response } = await apiClient.GET("/summary");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function importInvoices(file: File): Promise<ImportReport> {
  const body = new FormData();
  body.append("file", file, file.name);
  const response = await authorizedFetch("/invoices/import", { method: "POST", body });
  if (!response.ok) {
    throw await failure(response);
  }
  return (await response.json()) as ImportReport;
}

export function downloadImportErrors(importId: string): Promise<void> {
  return download(`/invoices/import/${importId}/errors.csv`, "facturas-con-errores.csv");
}

export function downloadImportTemplate(): Promise<void> {
  return download("/invoices/import-template.csv", "plantilla-facturas.csv");
}
