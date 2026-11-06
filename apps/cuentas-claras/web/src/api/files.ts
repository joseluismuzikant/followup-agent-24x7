import { apiError, type ApiRequestError } from "@followup/api-client-cuentas-claras";

import { authorizedFetch } from "./client";

export async function failure(response: Response): Promise<ApiRequestError> {
  const body: unknown = await response.json().catch(() => null);
  return apiError(response, body);
}

/** Saves a CSV the API answers with (the browser's download). */
export async function download(path: string, fileName: string): Promise<void> {
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
