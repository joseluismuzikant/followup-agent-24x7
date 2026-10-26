import { createApiClient } from "@followup/api-client-inmo24x7";

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export const apiClient = createApiClient(baseUrl);
