import { createClient } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";

import { envValue } from "./auth-mode";

let client: SupabaseClient | null = null;

/** Built on first use, so dev auth mode never constructs it. */
export function getSupabase(): SupabaseClient {
  client ??= createClient(
    envValue(import.meta.env.VITE_SUPABASE_URL) ?? "http://127.0.0.1:54321",
    envValue(import.meta.env.VITE_SUPABASE_ANON_KEY) ?? "local-anon-key",
  );
  return client;
}
