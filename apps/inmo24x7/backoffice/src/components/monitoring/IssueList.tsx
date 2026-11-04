import type { ErrorList, SentryIssue } from "@followup/api-client-inmo24x7";
import { Badge } from "@followup/ui";

import { formatDateTime } from "../../lib/labels";

export const projectLabels: Record<SentryIssue["project"], string> = {
  api: "API y worker",
  panel: "Panel",
  backoffice: "Backoffice",
};

/** Why there is no list: Sentry not configured, or not answering. Null when there is one. */
export function errorsUnavailableText(list: ErrorList): string | null {
  if (!list.configured) {
    return "Sentry no está configurado: faltan SENTRY_API_TOKEN, SENTRY_ORG y SENTRY_PROJECTS en la API (docs/go-live.md, «Monitoring»).";
  }
  if (!list.available) {
    return "Sentry no respondió. Probá de nuevo en un rato o entrá directo a Sentry.";
  }
  return null;
}

interface IssueListProps {
  issues: SentryIssue[];
  empty: string;
  showProject?: boolean;
}

/** Open issues, each linking to Sentry. */
export function IssueList({ issues, empty, showProject = true }: IssueListProps) {
  if (issues.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <ul className="flex flex-col divide-y text-sm">
      {issues.map((issue) => (
        <li key={issue.id} className="flex flex-wrap items-start justify-between gap-2 py-2">
          <div className="flex min-w-0 flex-col">
            <a
              href={issue.permalink}
              target="_blank"
              rel="noreferrer"
              className="truncate font-medium underline-offset-4 hover:underline"
            >
              {issue.title}
            </a>
            <span className="truncate text-xs text-muted-foreground">
              {issue.culprit ? `${issue.culprit} · ` : ""}
              Última vez {formatDateTime(issue.last_seen)}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            {showProject ? <Badge>{projectLabels[issue.project]}</Badge> : null}
            <span className="tabular-nums" title="Eventos">
              {issue.count} {issue.count === 1 ? "vez" : "veces"}
            </span>
            {issue.users ? <span className="text-muted-foreground">{issue.users} usuarios</span> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
