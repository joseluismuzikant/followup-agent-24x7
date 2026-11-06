import { canEditSetup } from "@followup/app-shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { fetchClient } from "../api/clients";
import { fetchMe } from "../api/me";
import { ClientFormDialog } from "../components/ClientFormDialog";
import { InvoiceDrawer } from "../components/InvoiceDrawer";
import { InvoiceStatusBadge } from "../components/InvoiceStatusBadge";
import { apiErrorMessage } from "../lib/api-errors";
import { formatAmount, shortDate, todayIso } from "../lib/format";
import { owed } from "./clientes";

export function ClientePage() {
  const { id = "" } = useParams();
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const clientQuery = useQuery({ queryKey: ["client", id], queryFn: () => fetchClient(id) });
  const client = clientQuery.data;
  const canEdit = meQuery.data ? canEditSetup(meQuery.data.profile.role) : false;

  if (clientQuery.isError) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(clientQuery.error, "No pudimos cargar el cliente.")}
        </p>
        <Link to="/clientes" className="text-sm text-primary">
          ← Volver a Clientes
        </Link>
      </div>
    );
  }
  if (!client) {
    return null;
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <Link to="/clientes" className="text-sm text-primary">
        ← Clientes
      </Link>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-xl">{client.name}</CardTitle>
            {client.subtitle ? <p className="text-sm text-muted-foreground">{client.subtitle}</p> : null}
          </div>
          {canEdit ? (
            <Button variant="outline" onClick={() => setEditing(true)}>
              Editar
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">CUIT</dt>
              <dd>{client.cuit ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Contacto</dt>
              <dd>{client.contact_name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">WhatsApp</dt>
              <dd>
                {client.missing_whatsapp ? (
                  <Badge tone="warning">Sin WhatsApp</Badge>
                ) : (
                  client.whatsapp_display
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd>{client.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Debe</dt>
              <dd className="tabular-nums">{owed(client)}</dd>
            </div>
            {client.notes ? (
              <div>
                <dt className="text-muted-foreground">Notas</dt>
                <dd>{client.notes}</dd>
              </div>
            ) : null}
          </dl>
        </CardContent>
      </Card>

      <section aria-label="Facturas del cliente" className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Facturas</h2>
        {client.invoices.length === 0 ? (
          <p className="text-sm text-muted-foreground">Este cliente no tiene facturas cargadas.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Factura</TableHead>
                  <TableHead className="text-right">Monto</TableHead>
                  <TableHead>Vence</TableHead>
                  <TableHead>Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {client.invoices.map((invoice) => (
                  <TableRow key={invoice.id} className="cursor-pointer" onClick={() => setSelected(invoice.id)}>
                    <TableCell className="whitespace-nowrap tabular-nums">{invoice.number}</TableCell>
                    <TableCell className="whitespace-nowrap text-right tabular-nums">
                      {formatAmount(invoice.amount, invoice.currency)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{shortDate(invoice.due_date)}</TableCell>
                    <TableCell>
                      <InvoiceStatusBadge
                        status={{
                          kind: invoice.status as "paid" | "overdue" | "due_soon" | "pending" | "cancelled",
                          label: invoice.status_label,
                          days_overdue: null,
                        }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <ClientFormDialog open={editing} client={client} onClose={() => setEditing(false)} />
      <InvoiceDrawer
        invoiceId={selected}
        canEdit={canEdit}
        today={todayIso()}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
