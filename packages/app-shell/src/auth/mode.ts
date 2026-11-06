export type AuthMode = "supabase" | "dev";

/** Vite passes unset variables from .env as "", so an empty value counts as unset. */
export function envValue(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/** `VITE_AUTH_MODE=dev` signs in with `dev:<email>` tokens; anything else uses Supabase. */
export function readAuthMode(value: string | undefined): AuthMode {
  return envValue(value) === "dev" ? "dev" : "supabase";
}
