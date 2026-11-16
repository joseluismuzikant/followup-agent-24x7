import type { PaymentPage } from "@followup/api-client-cuentas-claras";
import { ApiRequestError } from "@followup/api-client-cuentas-claras";
import { BrandMark, Button, Card, CardContent, CardHeader, CardTitle } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router";

import { fetchPaymentPage } from "../api/payments";
import { formatAmount, longDate } from "../lib/format";
import { PRODUCT_NAME } from "../lib/product";

/** Search engines never index a payment link. */
function useNoIndex() {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);
}

/** `/p/<token>`: what a reminder's "Ver y pagar" opens. No login: only what the link covers. */
export function PagoPage() {
  useNoIndex();
  const { token = "" } = useParams();
  const pageQuery = useQuery({
    queryKey: ["payment-page", token],
    queryFn: () => fetchPaymentPage(token),
    retry: false,
  });

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:py-12">
      <div className="mx-auto flex max-w-lg flex-col gap-6">
        {pageQuery.isPending ? (
          <p className="text-sm text-muted-foreground">Cargando...</p>
        ) : pageQuery.isError ? (
          <NotFound gone={pageQuery.error instanceof ApiRequestError && pageQuery.error.status === 404} />
        ) : (
          <Payment page={pageQuery.data} />
        )}
        <p className="text-center text-xs text-muted-foreground">
          Enviado con {PRODUCT_NAME}. Este link es personal: no lo compartas.
        </p>
      </div>
    </main>
  );
}

function NotFound({ gone }: { gone: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{gone ? "Este link ya no está disponible" : "No pudimos abrir el link"}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        {gone
          ? "El link no existe o venció. Si todavía tenés que pagar, pedile uno nuevo a quien te lo mandó."
          : "Probá de nuevo en unos minutos."}
      </CardContent>
    </Card>
  );
}

function Payment({ page }: { page: PaymentPage }) {
  const owed = page.totals.length > 0;
  return (
    <>
      <header className="flex items-center gap-3">
        <BrandMark name={page.business_name} />
        <div>
          <h1 className="text-xl font-semibold">{page.business_name}</h1>
          <p className="text-sm text-muted-foreground">Para {page.client_name}</p>
        </div>
      </header>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{owed ? "Facturas a pagar" : "Facturas"}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ul className="flex flex-col divide-y">
            {page.invoices.map((invoice) => (
              <li key={invoice.number} className="flex items-start justify-between gap-3 py-2 text-sm">
                <span>
                  <span className="block font-medium">{invoice.number}</span>
                  <span className="text-muted-foreground">
                    Vence el {longDate(invoice.due_date)} · {invoice.status_label}
                  </span>
                </span>
                <span className={invoice.paid ? "text-muted-foreground line-through" : "font-semibold tabular-nums"}>
                  {formatAmount(invoice.amount, invoice.currency)}
                </span>
              </li>
            ))}
          </ul>
          {owed ? (
            <div className="flex justify-between border-t pt-3 text-base font-semibold">
              <span>Total</span>
              <span className="tabular-nums">
                {page.totals.map((total) => formatAmount(total.amount, total.currency)).join(" + ")}
              </span>
            </div>
          ) : (
            <p className="rounded-md bg-success-soft p-3 text-sm text-emerald-800" role="status">
              ¡Listo! No hay nada pendiente en este link.
            </p>
          )}
        </CardContent>
      </Card>
      {owed ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cómo pagar</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <Button disabled className="w-full">
              Pronto vas a poder pagar con Mercado Pago
            </Button>
            {page.transfer ? (
              <section aria-label="Datos para transferencia" className="flex flex-col gap-1">
                <p className="font-medium">Por transferencia</p>
                <p>
                  <span className="text-muted-foreground">CBU / alias: </span>
                  <span className="font-mono">{page.transfer.cbu_or_alias}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">Titular: </span>
                  {page.transfer.holder}
                </p>
                {page.transfer.bank ? (
                  <p>
                    <span className="text-muted-foreground">Banco: </span>
                    {page.transfer.bank}
                  </p>
                ) : null}
                <p className="text-muted-foreground">
                  Cuando transfieras, respondé el WhatsApp con el comprobante.
                </p>
              </section>
            ) : (
              <p className="text-muted-foreground">
                Para pagar, respondé el WhatsApp y {page.business_name} te pasa los datos.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
