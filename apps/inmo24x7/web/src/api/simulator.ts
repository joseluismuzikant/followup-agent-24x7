import { apiError, type SimulatorReply, type SimulatorState } from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchSimulator(): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.GET("/simulator");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function sendSimulatorMessage(
  text: string,
  choiceId?: string,
): Promise<SimulatorReply> {
  const { data, error, response } = await apiClient.POST("/simulator/messages", {
    body: { text, choice_id: choiceId ?? null },
  });
  if (data) {
    return data;
  }
  throw apiError(response, error);
}

export async function resetSimulator(): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.POST("/simulator/reset");
  if (data) {
    return data;
  }
  throw apiError(response, error);
}
