import type { BusinessUsage, TenantUsage, UsageSplit } from "@followup/api-client-inmo24x7";
import {
  Badge,
  BarLineChart,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  KpiCard,
  PanelLayout,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useSearchParams } from "react-router";

import { downloadUsageCsv, fetchTenantUsage, fetchUsage } from "../api/backoffice";
import { RequireAdmin } from "../components/RequireAdmin";
import { apiErrorMessage } from "../lib/api-errors";
import {
  currentMonth,
  formatCost,
  formatCount,
  formatShare,
  monthLabel,
} from "../lib/labels";
import { navItems } from "../lib/nav";

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

const operationLabels: Record<string, string> = {
  extract: "Entender el mensaje",
  compose_reply: "Escribir la respuesta",
};

/** Consumo: LLM cost, conversations and WhatsApp templates per business, per UTC month. */
export function ConsumoPage() {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("mes") ?? "";
  const month = MONTH.test(requested) ? requested : currentMonth();
  const tenantId = params.get("negocio");

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    }
    setParams(next);
  };

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Consumo"
        description="Costo del LLM, conversaciones y plantillas de WhatsApp por negocio."
        navItems={navItems(location.pathname)}
        action={
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Mes</span>
            <Input
              type="month"
              aria-label="Mes"
              value={month}
              max={currentMonth()}
              onChange={(event) =>
                MONTH.test(event.target.value) ? update({ mes: event.target.value }) : undefined
              }
              className="w-40"
            />
          </label>
        }
      >
        <p className="mb-4 text-xs text-muted-foreground">
          Meses en UTC: lo que pasa después de las 21 h (Argentina) del último día cuenta en el mes
          siguiente. Meta cobra las plantillas aparte; acá solo se cuentan.
        </p>
        {tenantId ? (
          <TenantDetail
            tenantId={tenantId}
            month={month}
            onBack={() => update({ negocio: null })}
          />
        ) : (
          <Report month={month} onOpen={(id) => update({ negocio: id })} />
        )}
      </PanelLayout>
    </RequireAdmin>
  );
}

function Report({ month, onOpen }: { month: string; onOpen: (tenantId: string) => void }) {
  const query = useQuery({ queryKey: ["usage", month], queryFn: () => fetchUsage(month) });
  const download = useMutation({ mutationFn: () => downloadUsageCsv(month) });
  const report = query.data;

  if (query.isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(query.error, "No pudimos leer el consumo.")}
      </p>
    );
  }
  if (!report) {
    return <p className="text-sm text-muted-foreground">Cargando…</p>;
  }
  const totals = report.totals;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label={`Costo del LLM · ${monthLabel(report.month)}`}
          value={formatCost(totals.cost_usd, totals)}
          hint={
            totals.unpriced_calls
              ? `${formatCount(totals.unpriced_calls)} llamadas sin precio: el total está incompleto`
              : `${formatCount(totals.input_tokens)} tokens de entrada · ${formatCount(totals.output_tokens)} de salida`
          }
        />
        <KpiCard label="Conversaciones" value={formatCount(totals.conversations)} />
        <KpiCard label="Costo por conversación" value={formatCost(totals.cost_per_conversation_usd, totals)} />
        <KpiCard
          label="Parte del simulador"
          value={formatShare(totals.test_share)}
          hint={`${formatCount(totals.template_messages)} plantillas de WhatsApp`}
        />
      </div>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-base">Por negocio</CardTitle>
          <Button
            variant="outline"
            size="sm"
            disabled={download.isPending}
            onClick={() => download.mutate()}
          >
            Exportar CSV
          </Button>
        </CardHeader>
        <CardContent>
          {download.isError ? (
            <p className="mb-2 text-sm text-destructive" role="alert">
              {apiErrorMessage(download.error, "No pudimos descargar el archivo.")}
            </p>
          ) : null}
          <UsageTable rows={report.businesses} onOpen={onOpen} />
        </CardContent>
      </Card>
    </div>
  );
}

function UsageTable({ rows, onOpen }: { rows: BusinessUsage[]; onOpen: (id: string) => void }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Todavía no hay negocios.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Negocio</TableHead>
            <TableHead>Plan</TableHead>
            <TableHead className="text-right">Conversaciones</TableHead>
            <TableHead className="text-right">Llamadas</TableHead>
            <TableHead className="text-right">Tokens (entrada / salida)</TableHead>
            <TableHead className="text-right">Costo</TableHead>
            <TableHead className="text-right">Por conversación</TableHead>
            <TableHead className="text-right">Simulador</TableHead>
            <TableHead className="text-right">Plantillas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.tenant_id}>
              <TableCell>
                <button
                  type="button"
                  className="text-left font-medium underline-offset-4 hover:underline"
                  onClick={() => onOpen(row.tenant_id)}
                >
                  {row.name}
                </button>
              </TableCell>
              <TableCell>{row.plan === "pro" ? "Pro" : "Prueba"}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCount(row.figures.conversations)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCount(row.figures.llm_calls)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCount(row.figures.input_tokens)} / {formatCount(row.figures.output_tokens)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                <span className="inline-flex items-center gap-2">
                  {row.figures.unpriced_calls ? <Badge tone="warning">sin precio</Badge> : null}
                  {row.figures.unreported_calls && !row.figures.input_tokens ? (
                    <Badge>sin datos</Badge>
                  ) : null}
                  {formatCost(row.figures.cost_usd, row.figures)}
                </span>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCost(row.figures.cost_per_conversation_usd, row.figures)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatShare(row.figures.test_share)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatCount(row.figures.template_messages)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function TenantDetail({
  tenantId,
  month,
  onBack,
}: {
  tenantId: string;
  month: string;
  onBack: () => void;
}) {
  const query = useQuery({
    queryKey: ["usage", month, tenantId],
    queryFn: () => fetchTenantUsage(tenantId, month),
  });
  const detail = query.data;

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" size="sm" className="self-start" onClick={onBack}>
        ← Todos los negocios
      </Button>
      {query.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(query.error, "No pudimos leer el consumo del negocio.")}
        </p>
      ) : null}
      {detail ? <TenantUsageView detail={detail} /> : null}
    </div>
  );
}

function TenantUsageView({ detail }: { detail: TenantUsage }) {
  const figures = detail.business.figures;
  const chart = detail.daily.map((day) => ({
    label: String(Number(day.day.slice(8, 10))),
    title: day.day,
    bar: Number(day.cost_usd),
    line: day.conversations,
  }));
  return (
    <>
      <h2 className="text-lg font-semibold">
        {detail.business.name} · {monthLabel(detail.month)}
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Costo del LLM" value={formatCost(figures.cost_usd, figures)} />
        <KpiCard label="Conversaciones" value={formatCount(figures.conversations)} />
        <KpiCard label="Costo por conversación" value={formatCost(figures.cost_per_conversation_usd, figures)} />
        <KpiCard label="Parte del simulador" value={formatShare(figures.test_share)} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Por día</CardTitle>
          <CardDescription>Costo del LLM (barras) y conversaciones (línea), en UTC.</CardDescription>
        </CardHeader>
        <CardContent>
          <BarLineChart
            data={chart}
            barLabel="Costo (USD)"
            lineLabel="Conversaciones"
            formatBar={(value) => `US$ ${value.toFixed(2)}`}
            formatLine={(value) => String(value)}
          />
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <SplitCard title="Por tarea" rows={detail.by_operation} labels={operationLabels} />
        <SplitCard title="Por modelo" rows={detail.by_model} />
      </div>
    </>
  );
}

function SplitCard({
  title,
  rows,
  labels = {},
}: {
  title: string;
  rows: UsageSplit[];
  labels?: Record<string, string>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin llamadas este mes.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{title.replace("Por ", "")}</TableHead>
                <TableHead className="text-right">Llamadas</TableHead>
                <TableHead className="text-right">Costo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell className="font-mono text-xs">{labels[row.key] ?? row.key}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCount(row.llm_calls)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.unpriced_calls ? <Badge tone="warning">sin precio</Badge> : null}{" "}
                    {formatCost(row.cost_usd, row)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
