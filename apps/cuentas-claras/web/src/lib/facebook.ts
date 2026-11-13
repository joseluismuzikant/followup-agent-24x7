import { metaConfigFrom } from "@followup/app-shell";
import type { MetaConfig } from "@followup/app-shell";

/** Cuentas Claras's own Meta app (its own build variables: a Meta app has one webhook URL,
 * so each product has its own). Without them the panel offers the manual fallback. */
export function metaConfig(): MetaConfig | null {
  return metaConfigFrom({
    appId: import.meta.env.VITE_CUENTAS_CLARAS_META_APP_ID,
    configId: import.meta.env.VITE_CUENTAS_CLARAS_META_EMBEDDED_SIGNUP_CONFIG_ID,
    graphVersion: import.meta.env.VITE_META_GRAPH_API_VERSION,
  });
}
