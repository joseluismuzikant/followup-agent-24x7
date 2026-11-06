import { createClient } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";

import { envValue } from "./mode";

/** A Supabase client built on first use, so dev auth mode never constructs it. Both products
 * use the same Supabase project (one account per person). */
export function supabaseGetter(
  url: string | undefined,
  anonKey: string | undefined,
): () => SupabaseClient {
  let client: SupabaseClient | null = null;
  return () => {
    client ??= createClient(
      envValue(url) ?? "http://127.0.0.1:54321",
      envValue(anonKey) ?? "local-anon-key",
    );
    return client;
  };
}
