import { apiError } from "@followup/api-client-inmo24x7";
import type {
  IntegrationDelivery,
  Integrations,
  WebhookSaved,
  WidgetInput,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchIntegrations(): Promise<Integrations> {
  const { data, error, response } = await apiClient.GET("/integrations");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** "Probar conexión": Tokko is read once with the key; it is saved only if it works. */
export async function connectTokko(apiKey: string): Promise<Integrations> {
  const { data, error, response } = await apiClient.PUT("/integrations/tokko", {
    body: { api_key: apiKey },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function updateTokko(options: {
  import_properties: boolean;
  send_leads: boolean;
}): Promise<Integrations> {
  const { data, error, response } = await apiClient.PATCH("/integrations/tokko", {
    body: options,
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function disconnectTokko(): Promise<Integrations> {
  const { data, error, response } = await apiClient.DELETE("/integrations/tokko");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function syncTokko(): Promise<Integrations> {
  const { data, error, response } = await apiClient.POST("/integrations/tokko/sync");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function saveWebhook(url: string, enabled = true): Promise<WebhookSaved> {
  const { data, error, response } = await apiClient.PUT("/integrations/webhook", {
    body: { url, enabled },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function rotateWebhookSecret(): Promise<WebhookSaved> {
  const { data, error, response } = await apiClient.POST("/integrations/webhook/secret");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function deleteWebhook(): Promise<Integrations> {
  const { data, error, response } = await apiClient.DELETE("/integrations/webhook");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function testWebhook(): Promise<IntegrationDelivery> {
  const { data, error, response } = await apiClient.POST("/integrations/webhook/test");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function saveWidget(input: WidgetInput): Promise<Integrations> {
  const { data, error, response } = await apiClient.PUT("/integrations/widget", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function fetchLeadDeliveries(leadId: string): Promise<IntegrationDelivery[]> {
  const { data, error, response } = await apiClient.GET("/leads/{lead_id}/deliveries", {
    params: { path: { lead_id: leadId } },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
