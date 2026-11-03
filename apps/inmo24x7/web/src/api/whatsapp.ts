import { ApiRequestError, errorCode } from "@followup/api-client-inmo24x7";
import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchWhatsAppStatus(): Promise<WhatsAppStatus> {
  const { data, error, response } = await apiClient.GET("/whatsapp");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
