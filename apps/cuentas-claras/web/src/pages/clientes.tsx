import type { Client } from "@followup/api-client-cuentas-claras";
import { canEditSetup } from "@followup/app-shell";
import {
  Badge,
  Button,
  Input,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router";

import { fetchClients } from "../api/clients";
import { fetchMe } from "../api/me";
import { ClientFormDialog } from "../components/ClientFormDialog";
import { apiErrorMessage } from "../lib/api-errors";
import { formatAmount } from "../lib/format";

/** What a client owes, in pesos and (when any) dollars. */
export function owed(client: Pick<Client, "owed_ars" | "owed_usd">): string {
  const parts = [];
  if (Number(client.owed_ars) > 0) {
    parts.push(formatAmount(client.owed_ars));
  }
  if (Number(client.owed_usd) > 0) {
    parts.push(formatAmount(client.owed_usd, "USD"));
  }
  return parts.length > 0 ? parts.join(" + ") : "—";
}

export function ClientesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [missingWhatsapp, setMissingWhatsapp] = useState(false);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const q = useDeferredValue(search.trim());
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const clientsQuery = useQuery({
    queryKey: ["clients", q, missingWhatsapp, page],
    queryFn: () => fetchClients({ q, missingWhatsapp, page }),
    placeholderData: keepPreviousData,
  });
  const list = clientsQuery.data;
  const canEdit = meQuery.data ? canEditSetup(meQuery.data.profile.role) : false;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            type="search"
            aria-label="Buscar clientes"
            placeholder="Buscar por nombre, CUIT o contacto"
            className="w-72"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={missingWhatsapp}
              onChange={(event) => {
                setMissingWhatsapp(event.target.checked);
                setPage(1);
              }}
            />
            Solo sin WhatsApp
          </label>
        </div>
        {canEdit ? <Button onClick={() => setCreating(true)}>Nuevo cliente</Button> : null}
      </div>

      {clientsQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(clientsQuery.error, "No pudimos cargar los clientes. Probá de nuevo.")}
        </p>
      ) : null}

      {list ? (
        list.items.length === 0 ? (
          <p className="rounded-md border bg-card p-6 text-center text-sm text-muted-foreground">
            {q || missingWhatsapp
              ? "No hay clientes que coincidan."
              : "Todavía no tenés clientes. Se cargan solos al importar tus facturas."}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="overflow-x-auto rounded-md border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>CUIT</TableHead>
                    <TableHead>WhatsApp</TableHead>
                    <TableHead className="text-right">Facturas abiertas</TableHead>
                    <TableHead className="text-right">Debe</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.items.map((client) => (
                    <TableRow
                      key={client.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/clientes/${client.id}`)}
                    >
                      <TableCell>
                        <Link
                          to={`/clientes/${client.id}`}
                          className="font-medium"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {client.name}
                        </Link>
                        {client.subtitle ? (
                          <span className="block text-xs text-muted-foreground">{client.subtitle}</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{client.cuit ?? "—"}</TableCell>
                      <TableCell className="whitespace-nowrap">
                        {client.missing_whatsapp ? (
                          <Badge tone="warning">Sin WhatsApp</Badge>
                        ) : (
                          client.whatsapp_display
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{client.open_invoices}</TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{owed(client)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination page={list.page} pageSize={list.page_size} total={list.total} onPageChange={setPage} />
          </div>
        )
      ) : null}

      <ClientFormDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(client) => navigate(`/clientes/${client.id}`)}
      />
    </div>
  );
}
