import { apiError } from "@followup/api-client-cuentas-claras";
import type {
  PolicyInput,
  ReminderSettings,
  TemplateKind,
} from "@followup/api-client-cuentas-claras";

import { apiClient } from "./client";

export async function fetchReminders(): Promise<ReminderSettings> {
  const { data, error, response } = await apiClient.GET("/reminders");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function saveReminderPolicy(input: PolicyInput): Promise<ReminderSettings> {
  const { data, error, response } = await apiClient.PUT("/reminders", { body: input });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

/** A new version of the template, sent to Meta for review. */
export async function saveTemplateText(kind: TemplateKind, body: string): Promise<ReminderSettings> {
  const { data, error, response } = await apiClient.PUT("/reminders/templates/{kind}", {
    params: { path: { kind } },
    body: { body },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
