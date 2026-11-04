import type { MonitoringLinks } from "@followup/api-client-inmo24x7";

/** Grafana Explore with a LogQL query over the last day (empty without GRAFANA_URL). */
export function grafanaExploreUrl(links: MonitoringLinks | undefined, expr: string): string {
  if (!links?.grafana_url) {
    return "";
  }
  const datasource = { type: "loki", uid: links.loki_datasource };
  const panes = {
    a: {
      datasource: links.loki_datasource,
      queries: [{ refId: "A", expr, queryType: "range", datasource }],
      range: { from: "now-24h", to: "now" },
    },
  };
  return `${links.grafana_url}/explore?schemaVersion=1&orgId=1&panes=${encodeURIComponent(JSON.stringify(panes))}`;
}

/** Everything one business logged (tenant_id is a JSON field, not a label). */
export function tenantLogsQuery(tenantId: string): string {
  return `{environment="production"} | json | tenant_id="${tenantId}"`;
}

/** Everything one request logged. The panels show 8 characters of the id: a prefix match. */
export function requestLogsQuery(reference: string): string {
  return `{environment="production"} | json | request_id=~"${reference}.*"`;
}

/** Sentry's issue search (empty without SENTRY_ORG). */
export function sentrySearchUrl(links: MonitoringLinks | undefined, query: string): string {
  if (!links?.sentry_issues_url) {
    return "";
  }
  return `${links.sentry_issues_url}?query=${encodeURIComponent(query)}&statsPeriod=14d`;
}

/** A request id (or its first characters) as the panels show it: hex only. */
export function cleanReference(value: string): string {
  return value.trim().toLowerCase().replace(/[^0-9a-f]/g, "");
}
