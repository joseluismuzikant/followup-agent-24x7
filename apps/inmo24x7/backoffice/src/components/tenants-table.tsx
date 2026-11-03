import type { BusinessRow } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { Link } from "react-router";

import { badgeLabels, badgeTones, formatDate, planLabel } from "../lib/labels";

/** S8: one row per business. */
export function TenantsTable({ businesses }: { businesses: BusinessRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Negocio</TableHead>
          <TableHead>Plan</TableHead>
          <TableHead>Onboarding</TableHead>
          <TableHead>WhatsApp</TableHead>
          <TableHead className="text-right">Consultas (7 días)</TableHead>
          <TableHead>Alta</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {businesses.map((business) => (
          <TableRow key={business.id}>
            <TableCell>
              <Link
                to={`/negocios/${business.id}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {business.name}
              </Link>
              <span className="block text-xs text-muted-foreground">
                {business.owner_email ?? "Sin dueño"}
                {business.owner_pending ? " · todavía no entró" : ""}
              </span>
              {business.status === "suspended" ? (
                <Badge tone="danger" className="mt-1">
                  Suspendido
                </Badge>
              ) : null}
            </TableCell>
            <TableCell className="whitespace-nowrap">{planLabel(business.plan)}</TableCell>
            <TableCell className="whitespace-nowrap">
              {business.onboarding_done} de {business.onboarding_total}
            </TableCell>
            <TableCell>
              <Badge tone={badgeTones[business.whatsapp]}>{badgeLabels[business.whatsapp]}</Badge>
            </TableCell>
            <TableCell className="text-right">{business.leads_last_7_days}</TableCell>
            <TableCell className="whitespace-nowrap text-muted-foreground">
              {formatDate(business.created_at)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
