import type { LeadStatus } from "@followup/api-client-inmo24x7";
import { Badge } from "@followup/ui";

import { leadStatusLabels, leadStatusTones } from "../../lib/leads";

export function LeadStatusBadge({ status }: { status: LeadStatus }) {
  return <Badge tone={leadStatusTones[status]}>{leadStatusLabels[status]}</Badge>;
}
