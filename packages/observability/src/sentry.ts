import * as Sentry from "@sentry/react";
import type { Breadcrumb, ErrorEvent } from "@sentry/react";

import { scrubDeep, scrubText, withoutQuery } from "./scrub";

export type Area = "panel" | "backoffice";

export interface SentryOptions {
  /** VITE_SENTRY_DSN; empty = off. */
  dsn: string | undefined;
  release: string | undefined;
  environment: string | undefined;
  area: Area;
}

/** A 5xx from the API: status, path and request id only, never bodies. */
export interface ServerError {
  status: number;
  method: string;
  path: string;
  requestId: string | null;
}

// Parts of an event that may carry free text; ids, versions and SDK data are left alone.
const TEXT_PARTS = ["message", "exception", "breadcrumbs", "extra", "tags", "contexts"] as const;

export function scrubEvent(event: ErrorEvent): ErrorEvent {
  const scrubbed: ErrorEvent = { ...event };
  if (scrubbed.request) {
    scrubbed.request = {
      method: scrubbed.request.method,
      url: scrubbed.request.url ? withoutQuery(scrubbed.request.url) : undefined,
    };
  }
  if (scrubbed.user) {
    scrubbed.user = scrubbed.user.id ? { id: scrubbed.user.id } : {};
  }
  for (const part of TEXT_PARTS) {
    if (scrubbed[part] !== undefined) {
      (scrubbed as unknown as Record<string, unknown>)[part] = scrubDeep(scrubbed[part]);
    }
  }
  return scrubbed;
}

export function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb {
  const data = { ...crumb.data };
  for (const key of ["url", "from", "to"]) {
    if (typeof data[key] === "string") {
      data[key] = withoutQuery(data[key] as string);
    }
  }
  return {
    ...crumb,
    message: crumb.message ? scrubText(crumb.message) : crumb.message,
    data: scrubDeep(data),
  };
}

let active = false;

/** Starts Sentry for one panel; false (and nothing sent) without a DSN. */
export function initSentry({ dsn, release, environment, area }: SentryOptions): boolean {
  if (!dsn) {
    return false;
  }
  Sentry.init({
    dsn,
    release: release || undefined,
    environment: environment || "production",
    // What the SDK may collect at all; beforeSend below is the second lock.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      genAI: { inputs: false, outputs: false },
      databaseQueryData: false,
      stackFrameVariables: false,
    },
    // Errors only: no performance tracing, no session replay.
    tracesSampleRate: 0,
    integrations: (defaults) => defaults.filter((integration) => integration.name !== "Replay"),
    beforeSend: (event) => scrubEvent(event),
    beforeBreadcrumb: (crumb) => scrubBreadcrumb(crumb),
    initialScope: { tags: { area } },
  });
  active = true;
  return true;
}

/** The signed-in person by profile id only (never the email), and the business. */
export function identify(profileId: string | null, tenantId?: string | null): void {
  if (!active) {
    return;
  }
  Sentry.setUser(profileId ? { id: profileId } : null);
  Sentry.setTag("tenant_id", tenantId ?? undefined);
}

export function reportServerError(error: ServerError): void {
  if (!active) {
    return;
  }
  Sentry.captureMessage(`API ${error.status} ${error.method} ${error.path}`, {
    level: "error",
    tags: { request_id: error.requestId ?? undefined, status: String(error.status) },
    fingerprint: ["api-5xx", error.method, error.path.replace(/[0-9a-f-]{36}/g, ":id")],
  });
}

/** A forced error from this panel (Errores → "Enviar errores de prueba"). False when off. */
export function sendTestError(): boolean {
  if (!active) {
    return false;
  }
  Sentry.captureException(new Error("Error de prueba del panel (no es un problema real)."));
  return true;
}
