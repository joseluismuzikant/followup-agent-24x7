import type { Summary } from "@followup/api-client-cuentas-claras";
import { ConnectionErrorBanner } from "@followup/app-shell";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, KpiCard } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";
import { fetchSummary } from "../api/invoices";
import { ImportDialog } from "../components/ImportDialog";
import { useWhatsAppStatus } from "../components/WhatsAppSection";
import { SetupChecklist } from "../components/SetupChecklist";
import { apiErrorMessage } from "../lib/api-errors";
import { countLabel, formatAmount } from "../lib/format";

export function InicioPage() {
  const [importing, setImporting] = useState(false);
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });
  const summaryQuery = useQuery({ queryKey: ["summary"], queryFn: fetchSummary });
  const whatsapp = useWhatsAppStatus();
  const onboarding = onboardingQuery.data;
  const summary = summaryQuery.data;
  const empty = onboarding !== undefined && !onboarding.checklist.facts.invoices_loaded;

  return (
    <div className="flex flex-col gap-6">
      <ConnectionErrorBanner status={whatsapp.data} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {meQuery.data ? `Hola, ${meQuery.data.tenant.name}` : "Hola"}
          </h1>
          <p className="text-sm text-muted-foreground">Esto es lo que tenés para cobrar.</p>
        </div>
        <Button onClick={() => setImporting(true)}>Importar facturas</Button>
      </div>

      {summaryQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(summaryQuery.error, "No pudimos cargar el resumen. Probá de nuevo.")}
        </p>
      ) : null}

      {empty ? (
        <Card className="max-w-xl">
          <CardHeader>
            <CardTitle>Todavía no cargaste facturas</CardTitle>
            <CardDescription>
              Subí el Excel o CSV que exporta tu sistema de facturación y en un minuto ves qué
              está vencido y qué vence esta semana.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setImporting(true)}>Importar facturas</Button>
          </CardContent>
        </Card>
      ) : summary ? (
        <SummaryCards summary={summary} />
      ) : null}

      {onboarding ? (
        <SetupChecklist checklist={onboarding.checklist} wizardUnfinished={!onboarding.finished} />
      ) : null}

      <ImportDialog open={importing} onClose={() => setImporting(false)} />
    </div>
  );
}

function usdHint(amount: string, count: number): string | undefined {
  return count > 0 ? `y ${formatAmount(amount, "USD")} en dólares` : undefined;
}

export function SummaryCards({ summary }: { summary: Summary }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:max-w-2xl">
      <KpiCard
        label="Total a cobrar"
        value={formatAmount(summary.to_collect.amount)}
        hint={
          usdHint(summary.to_collect_usd.amount, summary.to_collect_usd.count) ??
          countLabel(summary.to_collect.count, "factura abierta", "facturas abiertas")
        }
      />
      <KpiCard
        label="Vencido"
        value={formatAmount(summary.overdue.amount)}
        hint={
          usdHint(summary.overdue_usd.amount, summary.overdue_usd.count) ??
          countLabel(summary.overdue.count, "factura vencida", "facturas vencidas")
        }
      />
    </div>
  );
}
