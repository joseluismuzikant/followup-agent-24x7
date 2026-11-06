import type { InvoiceTab, TabCounts } from "@followup/api-client-cuentas-claras";
import { canEditSetup } from "@followup/app-shell";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { fetchInvoices } from "../api/invoices";
import { fetchMe } from "../api/me";
import { ImportPanel } from "../components/ImportPanel";
import { InvoiceDrawer } from "../components/InvoiceDrawer";
import { InvoiceStatusBadge } from "../components/InvoiceStatusBadge";
import { apiErrorMessage } from "../lib/api-errors";
import { formatAmount, shortDate, todayIso } from "../lib/format";

export const tabs: { value: InvoiceTab; label: string }[] = [
  { value: "pending", label: "Pendientes" },
  { value: "overdue", label: "Vencidas" },
  { value: "promised", label: "Prometidas" },
  { value: "paid_this_month", label: "Pagadas este mes" },
];

export function FacturasPage() {
  const [tab, setTab] = useState<InvoiceTab>("pending");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [importing, setImporting] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const q = useDeferredValue(search.trim());
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const invoicesQuery = useQuery({
    queryKey: ["invoices", tab, q, page],
    queryFn: () => fetchInvoices({ tab, q, page }),
    placeholderData: keepPreviousData,
  });
  const list = invoicesQuery.data;
  const canEdit = meQuery.data ? canEditSetup(meQuery.data.profile.role) : false;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          type="search"
          aria-label="Buscar facturas"
          placeholder="Buscar por cliente, CUIT o número (0003-00001245)"
          className="max-w-md"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
        {canEdit ? (
          <Button variant={importing ? "outline" : "default"} onClick={() => setImporting(!importing)}>
            {importing ? "Cerrar la importación" : "Importar facturas"}
          </Button>
        ) : null}
      </div>

      {importing ? (
        <Card>
          <CardHeader>
            <CardTitle>Importar facturas</CardTitle>
            <CardDescription>
              Si una factura ya estaba cargada, la actualizamos. Las pagadas no se tocan.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ImportPanel />
          </CardContent>
        </Card>
      ) : null}

      <Tabs
        value={tab}
        counts={list?.counts}
        onChange={(value) => {
          setTab(value);
          setPage(1);
        }}
      />

      {invoicesQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(invoicesQuery.error, "No pudimos cargar las facturas. Probá de nuevo.")}
        </p>
      ) : null}

      {list ? (
        list.items.length === 0 ? (
          <p className="rounded-md border bg-card p-6 text-center text-sm text-muted-foreground">
            {q ? "No hay facturas que coincidan con la búsqueda." : "No hay facturas en esta pestaña."}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="overflow-x-auto rounded-md border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Factura</TableHead>
                    <TableHead className="text-right">Monto</TableHead>
                    <TableHead>Vence</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Lo próximo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.items.map((invoice) => (
                    <TableRow
                      key={invoice.id}
                      className="cursor-pointer"
                      onClick={() => setSelected(invoice.id)}
                    >
                      <TableCell>
                        <button
                          type="button"
                          className="text-left font-medium outline-none focus-visible:underline"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelected(invoice.id);
                          }}
                        >
                          {invoice.client_name}
                        </button>
                        {invoice.client_subtitle ? (
                          <span className="block text-xs text-muted-foreground">
                            {invoice.client_subtitle}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{invoice.number}</TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">
                        {formatAmount(invoice.amount, invoice.currency)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{shortDate(invoice.due_date)}</TableCell>
                      <TableCell>
                        <InvoiceStatusBadge status={invoice.status} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">{invoice.next_action ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <Pagination page={list.page} pageSize={list.page_size} total={list.total} onPageChange={setPage} />
          </div>
        )
      ) : null}

      <p className="text-xs text-muted-foreground">
        {/* Cuentas Claras tracks invoices; it does not issue them. */}
        Cuentas Claras no emite facturas ante ARCA: las cargás desde tu sistema de facturación
        y acá seguís su cobro.
      </p>

      <InvoiceDrawer
        invoiceId={selected}
        canEdit={canEdit}
        today={todayIso()}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

function Tabs({
  value,
  counts,
  onChange,
}: {
  value: InvoiceTab;
  counts: TabCounts | undefined;
  onChange: (value: InvoiceTab) => void;
}) {
  return (
    <div role="tablist" aria-label="Facturas por estado" className="flex flex-wrap gap-1 border-b">
      {tabs.map((tab) => {
        const selected = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.value)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
              selected
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {counts ? `${tab.label} (${counts[tab.value]})` : tab.label}
          </button>
        );
      })}
    </div>
  );
}
