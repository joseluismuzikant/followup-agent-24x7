import { sendTestError } from "@followup/observability";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  PanelLayout,
  SegmentedControl,
} from "@followup/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation } from "react-router";

import {
  fetchErrors,
  fetchSystemHealth,
  triggerApiTestError,
  type ErrorPeriod,
  type ErrorProject,
} from "../api/backoffice";
import { IssueList, errorsUnavailableText } from "../components/monitoring/IssueList";
import { RequireAdmin } from "../components/RequireAdmin";
import { apiErrorMessage } from "../lib/api-errors";
import {
  cleanReference,
  grafanaExploreUrl,
  requestLogsQuery,
  sentrySearchUrl,
} from "../lib/monitoring";
import { navItems } from "../lib/nav";

const projects = [
  { value: "all", label: "Todos" },
  { value: "api", label: "API y worker" },
  { value: "panel", label: "Panel" },
  { value: "backoffice", label: "Backoffice" },
] as const;

const periods = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 días" },
  { value: "14d", label: "14 días" },
] as const;

/** Errores: open Sentry issues, and a search by the "código de referencia" customers see. */
export function ErroresPage() {
  const location = useLocation();
  const [project, setProject] = useState<ErrorProject>("all");
  const [period, setPeriod] = useState<ErrorPeriod>("24h");
  const query = useQuery({
    queryKey: ["errors", project, period],
    queryFn: () => fetchErrors({ project, period, limit: 50 }),
  });
  const list = query.data;
  const unavailable = list ? errorsUnavailableText(list) : null;

  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="Errores"
        description="Errores abiertos en Sentry de la API, el worker y los dos paneles."
        navItems={navItems(location.pathname)}
        action={
          list?.sentry_issues_url ? (
            <Button asChild variant="outline">
              <a href={list.sentry_issues_url} target="_blank" rel="noreferrer">
                Ver todos en Sentry
              </a>
            </Button>
          ) : null
        }
      >
        <div className="flex flex-col gap-6">
          <ReferenceSearch />
          <TestErrors />
          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="text-base">Errores abiertos</CardTitle>
              <div className="flex flex-wrap gap-2">
                <SegmentedControl ariaLabel="Proyecto" options={projects} value={project} onChange={setProject} />
                <SegmentedControl ariaLabel="Período" options={periods} value={period} onChange={setPeriod} />
              </div>
            </CardHeader>
            <CardContent>
              {query.isError ? (
                <p className="text-sm text-destructive" role="alert">
                  {apiErrorMessage(query.error, "No pudimos leer los errores.")}
                </p>
              ) : null}
              {query.isPending ? <p className="text-sm text-muted-foreground">Cargando…</p> : null}
              {unavailable ? (
                <p className="text-sm text-muted-foreground" role="status">
                  {unavailable}
                </p>
              ) : null}
              {list && !unavailable ? (
                <IssueList issues={list.issues} empty="No hay errores abiertos en este período." />
              ) : null}
            </CardContent>
          </Card>
        </div>
      </PanelLayout>
    </RequireAdmin>
  );
}

/** A customer reports "Código de referencia: 1a2b3c4d": its logs in Grafana and its errors in
 * Sentry. */
function ReferenceSearch() {
  const system = useQuery({ queryKey: ["system"], queryFn: fetchSystemHealth });
  const [value, setValue] = useState("");
  const reference = cleanReference(value);
  const links = system.data?.links;
  const logs = reference ? grafanaExploreUrl(links, requestLogsQuery(reference)) : "";
  const sentry = reference ? sentrySearchUrl(links, `request_id:${reference}*`) : "";
  const nothingConfigured = system.data && !links?.grafana_url && !links?.sentry_issues_url;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Buscar por código de referencia</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <FormField
          label="Código de referencia"
          htmlFor="reference"
          hint="El que ve el cliente en un error del panel (8 caracteres)."
        >
          <Input
            id="reference"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="1a2b3c4d"
            autoComplete="off"
          />
        </FormField>
        <div className="flex flex-wrap gap-2">
          {logs ? (
            <Button asChild variant="outline" size="sm">
              <a href={logs} target="_blank" rel="noreferrer">
                Ver logs en Grafana
              </a>
            </Button>
          ) : null}
          {sentry ? (
            <Button asChild variant="outline" size="sm">
              <a href={sentry} target="_blank" rel="noreferrer">
                Buscar en Sentry
              </a>
            </Button>
          ) : null}
        </div>
        {nothingConfigured ? (
          <p className="text-xs text-muted-foreground">
            Configurá GRAFANA_URL o SENTRY_ORG en la API para buscar desde acá.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Checks Sentry end to end: one error from the API and one from this panel. */
function TestErrors() {
  const send = useMutation({
    mutationFn: async () => ({ reference: await triggerApiTestError(), panel: sendTestError() }),
  });
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <Button variant="outline" size="sm" disabled={send.isPending} onClick={() => send.mutate()}>
        Enviar errores de prueba
      </Button>
      {send.data ? (
        <span role="status" className="text-muted-foreground">
          Enviados. En un minuto aparecen en Sentry como «Error de prueba»
          {send.data.reference ? ` (código de referencia ${send.data.reference})` : ""}
          {send.data.panel ? "." : "; el del panel no, porque este build no tiene VITE_SENTRY_DSN."}
        </span>
      ) : null}
      {send.isError ? (
        <span role="alert" className="text-destructive">
          {apiErrorMessage(send.error, "No pudimos enviar el error de prueba.")}
        </span>
      ) : null}
    </div>
  );
}
