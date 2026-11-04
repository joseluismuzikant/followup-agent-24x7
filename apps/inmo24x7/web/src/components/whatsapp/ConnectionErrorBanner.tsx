import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { Button } from "@followup/ui";
import { Link } from "react-router";

import { timeAgo } from "../../lib/leads";

/** Red banner on Inicio and Configuración while the WhatsApp connection is in error. */
export function ConnectionErrorBanner({
  status,
  onReconnect,
}: {
  status: WhatsAppStatus | undefined;
  /** Runs Embedded Signup in place; without it the button goes to Configuración. */
  onReconnect?: () => void;
}) {
  if (status?.status !== "error" || !status.error) {
    return null;
  }
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-rose-900"
    >
      <div className="flex flex-col gap-1 text-sm">
        <p className="font-medium">{status.error.title}</p>
        <p>
          {status.error.message}
          {status.failing_since
            ? ` Los mensajes no salen desde ${timeAgo(status.failing_since)}.`
            : ""}
        </p>
        <p>{status.error.action}</p>
      </div>
      {onReconnect ? (
        <Button variant="outline" size="sm" onClick={onReconnect}>
          Volver a conectar
        </Button>
      ) : (
        <Button asChild variant="outline" size="sm">
          <Link to="/configuracion#whatsapp">Volver a conectar</Link>
        </Button>
      )}
    </div>
  );
}
