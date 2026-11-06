import { readAuthMode } from "@followup/app-shell";

export { envValue, readAuthMode, type AuthMode } from "@followup/app-shell";

export const authMode = readAuthMode(import.meta.env.VITE_AUTH_MODE);
