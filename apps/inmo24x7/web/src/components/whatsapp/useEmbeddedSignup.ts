/** Moved to @followup/app-shell (shared with Cuentas Claras); here with inmo24x7's API, its
 * Meta app and its error copy. */
import { useEmbeddedSignup as useSharedSignup } from "@followup/app-shell";

import type { WhatsAppPanelApi } from "@followup/app-shell";

import * as whatsappApi from "../../api/whatsapp";
import { apiErrorMessage } from "../../lib/api-errors";
import { metaConfig } from "../../lib/facebook";

/** Read when called (tests replace the module's functions). */
const PANEL_API: WhatsAppPanelApi = {
  completeEmbeddedSignup: (input) => whatsappApi.completeEmbeddedSignup(input),
  retryEmbeddedSignup: () => whatsappApi.retryEmbeddedSignup(),
  reportSignupAbandoned: (input) => whatsappApi.reportSignupAbandoned(input),
};

export type { SignupState } from "@followup/app-shell";

export function useEmbeddedSignup() {
  return useSharedSignup(
    PANEL_API,
    metaConfig(),
    apiErrorMessage,
  );
}
