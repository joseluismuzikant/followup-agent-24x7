import { apiError } from "@followup/api-client-cuentas-claras";
import type {
  PaymentPage,
  PaymentSettings,
  TransferInput,
} from "@followup/api-client-cuentas-claras";

import { apiClient } from "./client";

/** The public page behind a reminder's link (no login). */
export async function fetchPaymentPage(token: string): Promise<PaymentPage> {
  const { data, error, response } = await apiClient.GET("/pay/{token}", {
    params: { path: { token } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchPaymentSettings(): Promise<PaymentSettings> {
  const { data, error, response } = await apiClient.GET("/payment-settings");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function saveTransferDetails(input: TransferInput): Promise<PaymentSettings> {
  const { data, error, response } = await apiClient.PUT("/payment-settings", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
