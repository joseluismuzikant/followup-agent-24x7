/** Moved to @followup/app-shell (shared with Cuentas Claras's backoffice); here with
 * inmo24x7's API, error copy and its visit confirmation template. */
import { WhatsAppConnectionPanel as SharedPanel } from "@followup/app-shell";

import type { WhatsAppAdminApi } from "@followup/app-shell";

import * as whatsappApi from "../api/whatsapp";
import { apiErrorMessage } from "../lib/api-errors";

export { ConnectionStatusCard } from "@followup/app-shell";

/** Read when called (tests replace the module's functions). */
const ADMIN_API: WhatsAppAdminApi = {
  fetchConnection: (tenantId) => whatsappApi.fetchConnection(tenantId),
  saveConnection: (tenantId, input) => whatsappApi.saveConnection(tenantId, input),
  runConnectionAction: (tenantId, action) => whatsappApi.runConnectionAction(tenantId, action),
  sendTestMessage: (tenantId, to) => whatsappApi.sendTestMessage(tenantId, to),
};

export function WhatsAppConnectionPanel({
  tenantId,
  onSaved,
}: {
  tenantId: string;
  /** Called after every change, so the S9 card shows the new state. */
  onSaved?: () => void;
}) {
  return (
    <SharedPanel
      tenantId={tenantId}
      api={ADMIN_API}
      describeError={apiErrorMessage}
      visitTemplate
      onSaved={onSaved}
    />
  );
}
