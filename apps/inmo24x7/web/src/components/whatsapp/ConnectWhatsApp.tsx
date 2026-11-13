import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { ConnectWhatsApp as SharedConnectWhatsApp } from "@followup/app-shell";

import type { WhatsAppPanelApi } from "@followup/app-shell";

import * as whatsappApi from "../../api/whatsapp";
import { apiErrorMessage } from "../../lib/api-errors";
import { metaConfig } from "../../lib/facebook";
import { INMO_WHATSAPP_COPY } from "../WhatsAppStatusCard";

/** Read when called (tests replace the module's functions). */
const PANEL_API: WhatsAppPanelApi = {
  completeEmbeddedSignup: (input) => whatsappApi.completeEmbeddedSignup(input),
  retryEmbeddedSignup: () => whatsappApi.retryEmbeddedSignup(),
  reportSignupAbandoned: (input) => whatsappApi.reportSignupAbandoned(input),
};

export { META_LINKS } from "@followup/app-shell";

/** S4, shared by wizard step 4 and Configuración → WhatsApp (@followup/app-shell), with
 * inmo24x7's API, Meta app and copy. */
export function ConnectWhatsApp({ status }: { status: WhatsAppStatus | undefined }) {
  return (
    <SharedConnectWhatsApp
      status={status}
      api={PANEL_API}
      config={metaConfig()}
      describeError={apiErrorMessage}
      copy={INMO_WHATSAPP_COPY}
    />
  );
}
