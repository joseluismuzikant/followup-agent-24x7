import type { InvoiceDetail, PaidVia } from "@followup/api-client-cuentas-claras";
import { Button, Dialog, FormField, Input } from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router";

import { cancelInvoice, fetchInvoice, markInvoicePaid, updateInvoice } from "../api/invoices";
import { apiErrorMessage } from "../lib/api-errors";
import { formatAmount, longDate } from "../lib/format";
import { InvoiceStatusBadge } from "./InvoiceStatusBadge";

const paidViaOptions: { value: PaidVia; label: string }[] = [
  { value: "transfer", label: "Transferencia" },
  { value: "mercado_pago", label: "Mercado Pago" },
  { value: "manual", label: "Efectivo o cheque" },
  { value: "other", label: "Otro" },
];

const selectClass =
  "h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

type Mode = "view" | "pay" | "cancel" | "edit";

interface InvoiceDrawerProps {
  invoiceId: string | null;
  canEdit: boolean;
  /** Today in the business's timezone (YYYY-MM-DD): the default payment date. */
  today: string;
  onClose: () => void;
}

/** A row of Facturas, in full: the invoice, its client, the payment, and the actions. */
export function InvoiceDrawer({ invoiceId, canEdit, today, onClose }: InvoiceDrawerProps) {
  const [mode, setMode] = useState<Mode>("view");
  const invoiceQuery = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () => fetchInvoice(invoiceId!),
    enabled: invoiceId !== null,
  });
  const invoice = invoiceQuery.data;

  function close() {
    setMode("view");
    onClose();
  }

  return (
    <Dialog
      open={invoiceId !== null}
      variant="drawer"
      title={invoice ? `Factura ${invoice.number}` : "Factura"}
      onClose={close}
    >
      {invoiceQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(invoiceQuery.error, "No pudimos cargar la factura.")}
        </p>
      ) : null}
      {invoice ? (
        mode === "pay" ? (
          <MarkPaidForm invoice={invoice} today={today} onDone={() => setMode("view")} />
        ) : mode === "cancel" ? (
          <CancelForm invoice={invoice} onDone={() => setMode("view")} />
        ) : mode === "edit" ? (
          <EditForm invoice={invoice} onDone={() => setMode("view")} />
        ) : (
          <InvoiceView invoice={invoice} canEdit={canEdit} onMode={setMode} />
        )
      ) : null}
    </Dialog>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

function InvoiceView({
  invoice,
  canEdit,
  onMode,
}: {
  invoice: InvoiceDetail;
  canEdit: boolean;
  onMode: (mode: Mode) => void;
}) {
  const open = invoice.lifecycle === "open";

  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Factura" className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-2xl font-semibold tabular-nums">
            {formatAmount(invoice.amount, invoice.currency)}
          </p>
          <InvoiceStatusBadge status={invoice.status} />
        </div>
        <dl className="flex flex-col gap-1">
          <Row label="Emitida">{longDate(invoice.issue_date)}</Row>
          <Row label="Vence">{longDate(invoice.due_date)}</Row>
          {invoice.description ? <Row label="Detalle">{invoice.description}</Row> : null}
          <Row label="Lo próximo">{invoice.next_action ?? "—"}</Row>
        </dl>
      </section>

      <section aria-label="Cliente" className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">Cliente</h3>
        <dl className="flex flex-col gap-1">
          <Row label="Nombre">
            <Link
              to={`/clientes/${invoice.client.id}`}
              className="text-primary underline-offset-4 hover:underline"
            >
              {invoice.client.name}
            </Link>
          </Row>
          {invoice.client.cuit ? <Row label="CUIT">{invoice.client.cuit}</Row> : null}
          {invoice.client.contact_name ? (
            <Row label="Contacto">{invoice.client.contact_name}</Row>
          ) : null}
          <Row label="WhatsApp">{invoice.client.whatsapp_display ?? "Sin WhatsApp"}</Row>
          {invoice.client.email ? <Row label="Email">{invoice.client.email}</Row> : null}
        </dl>
      </section>

      {invoice.payment ? (
        <section aria-label="Pago" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Pago</h3>
          <dl className="flex flex-col gap-1">
            <Row label="Fecha">{longDate(invoice.payment.paid_at)}</Row>
            <Row label="Medio">{invoice.payment.paid_via_label}</Row>
            {invoice.payment.reference ? (
              <Row label="Referencia">{invoice.payment.reference}</Row>
            ) : null}
          </dl>
        </section>
      ) : null}

      {invoice.cancelled_reason ? (
        <p className="text-sm text-muted-foreground">Anulada: {invoice.cancelled_reason}</p>
      ) : null}

      {canEdit && open ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onMode("pay")}>Marcar como pagada</Button>
          <Button variant="outline" onClick={() => onMode("edit")}>
            Editar
          </Button>
          <Button variant="ghost" onClick={() => onMode("cancel")}>
            Anular
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function useInvoiceMutation<T>(action: (input: T) => Promise<InvoiceDetail>, onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSuccess: async (invoice) => {
      queryClient.setQueryData(["invoice", invoice.id], invoice);
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
      await queryClient.invalidateQueries({ queryKey: ["clients"] });
      await queryClient.invalidateQueries({ queryKey: ["client"] });
      onDone();
    },
  });
}

function FormActions({
  saving,
  label,
  error,
  onCancel,
}: {
  saving: boolean;
  label: string;
  error: string | null;
  onCancel: () => void;
}) {
  return (
    <>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Guardando..." : label}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Volver
        </Button>
      </div>
    </>
  );
}

function MarkPaidForm({
  invoice,
  today,
  onDone,
}: {
  invoice: InvoiceDetail;
  today: string;
  onDone: () => void;
}) {
  const [paidAt, setPaidAt] = useState(today);
  const [paidVia, setPaidVia] = useState<PaidVia>("transfer");
  const [reference, setReference] = useState("");
  const mutation = useInvoiceMutation(
    () =>
      markInvoicePaid(invoice.id, {
        paid_at: paidAt,
        paid_via: paidVia,
        reference: reference.trim() || null,
      }),
    onDone,
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate(undefined);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-label="Marcar como pagada">
      <p className="text-sm text-muted-foreground">
        {invoice.client.name} · {formatAmount(invoice.amount, invoice.currency)}
      </p>
      <FormField label="Fecha de pago" htmlFor="paid-at">
        <Input
          id="paid-at"
          type="date"
          value={paidAt}
          max={today}
          onChange={(event) => setPaidAt(event.target.value)}
        />
      </FormField>
      <FormField label="Medio de pago" htmlFor="paid-via">
        <select
          id="paid-via"
          value={paidVia}
          onChange={(event) => setPaidVia(event.target.value as PaidVia)}
          className={selectClass}
        >
          {paidViaOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FormField>
      <FormField label="Referencia (opcional)" htmlFor="paid-reference" hint="Número de operación o comprobante.">
        <Input
          id="paid-reference"
          value={reference}
          maxLength={120}
          onChange={(event) => setReference(event.target.value)}
        />
      </FormField>
      <FormActions
        saving={mutation.isPending}
        label="Marcar como pagada"
        error={
          mutation.isError
            ? apiErrorMessage(mutation.error, "No pudimos marcarla como pagada. Probá de nuevo.")
            : null
        }
        onCancel={onDone}
      />
    </form>
  );
}

function CancelForm({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useInvoiceMutation(() => cancelInvoice(invoice.id, reason.trim()), onDone);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) {
      setLocalError("Contanos por qué la anulás.");
      return;
    }
    setLocalError(null);
    mutation.mutate(undefined);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-label="Anular la factura">
      <p className="text-sm text-muted-foreground">
        La factura deja de contar como deuda. No se anula en ARCA: eso lo hacés desde tu sistema
        de facturación.
      </p>
      <FormField label="Motivo" htmlFor="cancel-reason">
        <Input
          id="cancel-reason"
          value={reason}
          maxLength={500}
          placeholder="Se emitió una nota de crédito"
          onChange={(event) => setReason(event.target.value)}
        />
      </FormField>
      <FormActions
        saving={mutation.isPending}
        label="Anular"
        error={
          localError ??
          (mutation.isError
            ? apiErrorMessage(mutation.error, "No pudimos anularla. Probá de nuevo.")
            : null)
        }
        onCancel={onDone}
      />
    </form>
  );
}

function EditForm({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const [issueDate, setIssueDate] = useState(invoice.issue_date);
  const [dueDate, setDueDate] = useState(invoice.due_date);
  const [amount, setAmount] = useState(invoice.amount);
  const [currency, setCurrency] = useState(invoice.currency);
  const [description, setDescription] = useState(invoice.description);
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useInvoiceMutation(
    () =>
      updateInvoice(invoice.id, {
        client_id: invoice.client.id,
        invoice_type: invoice.invoice_type,
        point_of_sale: invoice.point_of_sale,
        number: invoice.invoice_number,
        issue_date: issueDate,
        due_date: dueDate,
        amount: amount.replace(",", "."),
        currency,
        description,
      }),
    onDone,
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = Number(amount.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setLocalError("El monto tiene que ser un número mayor a cero.");
      return;
    }
    if (dueDate < issueDate) {
      setLocalError("El vencimiento no puede ser anterior a la emisión.");
      return;
    }
    setLocalError(null);
    mutation.mutate(undefined);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-label="Editar la factura">
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Emisión" htmlFor="edit-issue">
          <Input
            id="edit-issue"
            type="date"
            value={issueDate}
            onChange={(event) => setIssueDate(event.target.value)}
          />
        </FormField>
        <FormField label="Vencimiento" htmlFor="edit-due">
          <Input
            id="edit-due"
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </FormField>
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-3">
        <FormField label="Monto" htmlFor="edit-amount">
          <Input
            id="edit-amount"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </FormField>
        <FormField label="Moneda" htmlFor="edit-currency">
          <select
            id="edit-currency"
            value={currency}
            onChange={(event) => setCurrency(event.target.value as "ARS" | "USD")}
            className={selectClass}
          >
            <option value="ARS">Pesos</option>
            <option value="USD">Dólares</option>
          </select>
        </FormField>
      </div>
      <FormField label="Detalle" htmlFor="edit-description">
        <Input
          id="edit-description"
          value={description}
          maxLength={500}
          onChange={(event) => setDescription(event.target.value)}
        />
      </FormField>
      <FormActions
        saving={mutation.isPending}
        label="Guardar cambios"
        error={
          localError ??
          (mutation.isError
            ? apiErrorMessage(mutation.error, "No pudimos guardar la factura. Probá de nuevo.")
            : null)
        }
        onCancel={onDone}
      />
    </form>
  );
}
