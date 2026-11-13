import type { InvoiceStatus } from "@followup/api-client-cuentas-claras";
import { Badge } from "@followup/ui";

const tones = {
  paid: "success",
  overdue: "danger",
  due_soon: "warning",
  pending: "neutral",
  promised: "info",
  cancelled: "neutral",
} as const;

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return <Badge tone={tones[status.kind]}>{status.label}</Badge>;
}
