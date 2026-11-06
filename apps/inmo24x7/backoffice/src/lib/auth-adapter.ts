import { pickAdapter } from "@followup/app-shell";
import type { AuthAdapter } from "@followup/app-shell";

import { authMode } from "./auth-mode";
import { getSupabase } from "./supabase";

export { devAdapter, type AuthAdapter, type AuthSession } from "@followup/app-shell";

/** Dev tokens or Supabase, as VITE_AUTH_MODE says. */
export function authAdapter(): AuthAdapter {
  return pickAdapter(authMode, getSupabase);
}

export async function getAccessToken(): Promise<string | null> {
  return (await authAdapter().getSession())?.accessToken ?? null;
}
