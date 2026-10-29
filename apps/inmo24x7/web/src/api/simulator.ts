import {
  ApiRequestError,
  errorCode,
  type SimulatorReply,
  type SimulatorState,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchSimulator(): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.GET("/simulator");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function sendSimulatorMessage(text: string): Promise<SimulatorReply> {
  const { data, error, response } = await apiClient.POST("/simulator/messages", {
    body: { text },
  });
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function resetSimulator(): Promise<SimulatorState> {
  const { data, error, response } = await apiClient.POST("/simulator/reset");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
