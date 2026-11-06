import { supabaseGetter } from "@followup/app-shell";

/** Built on first use, so dev auth mode never constructs it. */
export const getSupabase = supabaseGetter(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
);
