import {
  ApiRequestError,
  errorCode,
  type AgentSetup,
  type AgentSetupInput,
  type AgentVersion,
} from "@followup/api-client-inmo24x7";

import { apiClient } from "./client";

export async function fetchAgentSetup(): Promise<AgentSetup> {
  const { data, error, response } = await apiClient.GET("/agent-setup");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function saveAgentSetup(input: AgentSetupInput): Promise<AgentSetup> {
  const { data, error, response } = await apiClient.PUT("/agent-setup", { body: input });
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}

export async function fetchAgentVersions(): Promise<AgentVersion[]> {
  const { data, error, response } = await apiClient.GET("/agent-setup/versions");
  if (data) {
    return data;
  }
  throw new ApiRequestError(response.status, errorCode(error));
}
