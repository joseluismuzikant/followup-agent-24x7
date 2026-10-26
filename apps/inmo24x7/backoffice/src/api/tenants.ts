import type { components } from "./schema";

export type Tenant = components["schemas"]["TenantRead"];

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

export async function fetchTenants(): Promise<Tenant[]> {
  const response = await fetch(`${API_URL}/tenants`);

  if (!response.ok) {
    throw new Error("No pudimos cargar los negocios.");
  }

  return response.json() as Promise<Tenant[]>;
}
