import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { cn } from "@followup/ui";

import { timeAgo } from "../lib/leads";

interface Row {
  label: string;
  value: string;
  ok: boolean;
}

function rows(status: WhatsAppStatus): Row[] {
  const connected = status.status === "connected";
  const number = [status.display_phone_number, status.verified_name].filter(Boolean).join(" · ");
  const received = Boolean(status.last_inbound_at);
  return [
    {
      label: "Cuenta de Meta",
      value:
        status.status === "error"
          ? "Hay un problema con la conexión. Ya nos avisaron."
          : connected
            ? "Conectada"
            : "Desconectada",
      ok: connected,
    },
    { label: "Número", value: number || "Pendiente", ok: Boolean(status.display_phone_number) },
    {
      label: "Recepción de mensajes",
      value: received && status.last_inbound_at
        ? `Funcionando · último mensaje ${timeAgo(status.last_inbound_at)}`
        : "Esperando el primer mensaje",
      ok: received,
    },
    {
      label: "Mensaje de prueba",
      value: received ? "Recibido" : "Escribile a tu número desde otro teléfono para probarlo",
      ok: received,
    },
  ];
}

/** S4: how the WhatsApp connection is doing, in plain words. */
export function WhatsAppStatusCard({ status }: { status: WhatsAppStatus }) {
  return (
    <section aria-label="Estado de WhatsApp" className="flex flex-col gap-2 rounded-lg border p-4">
      {rows(status).map((row) => (
        <div key={row.label} className="flex items-start gap-3 text-sm">
          <span
            aria-hidden="true"
            className={cn(
              "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs",
              row.ok ? "bg-emerald-100 text-emerald-800" : "bg-muted text-muted-foreground",
            )}
          >
            {row.ok ? "✓" : "•"}
          </span>
          <span>
            <span className="block font-medium">{row.label}</span>
            <span className="text-muted-foreground">{row.value}</span>
          </span>
        </div>
      ))}
    </section>
  );
}
