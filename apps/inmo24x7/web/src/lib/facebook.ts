/** Moved to @followup/app-shell (shared with Cuentas Claras); inmo24x7's Meta app comes
 * from its own build variables. */
import { metaConfigFrom } from "@followup/app-shell";
import type { MetaConfig } from "@followup/app-shell";

export {
  isFacebookOrigin,
  loadFacebookSdk,
  parseSignupMessage,
  type MetaConfig,
  type SignupEvent,
} from "@followup/app-shell";

export function metaConfig(): MetaConfig | null {
  return metaConfigFrom({
    appId: import.meta.env.VITE_META_APP_ID,
    configId: import.meta.env.VITE_META_EMBEDDED_SIGNUP_CONFIG_ID,
    graphVersion: import.meta.env.VITE_META_GRAPH_API_VERSION,
  });
}
