import type { ErrorEvent } from "@sentry/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sentry = vi.hoisted(() => ({
  init: vi.fn(),
  captureMessage: vi.fn(),
  setUser: vi.fn(),
  setTag: vi.fn(),
}));
vi.mock("@sentry/react", () => sentry);

const { identify, initSentry, reportServerError, scrubBreadcrumb, scrubEvent } = await import(
  "./sentry"
);

describe("scrubEvent", () => {
  it("keeps the error and drops PII, query strings and everything about the user but the id", () => {
    const event = scrubEvent({
      type: undefined,
      message: "failed for ana@example.com",
      exception: { values: [{ type: "Error", value: "phone +54 9 11 5555-1234" }] },
      request: {
        url: "https://app.example.com/consultas?q=ana@example.com",
        method: "GET",
        headers: { Cookie: "x" },
        cookies: { session: "s" },
        query_string: "q=ana",
      },
      user: { id: "profile-1", email: "ana@example.com", ip_address: "1.2.3.4" },
    } as ErrorEvent);

    expect(event.request).toEqual({ method: "GET", url: "https://app.example.com/consultas" });
    expect(event.user).toEqual({ id: "profile-1" });
    expect(event.message).toBe("failed for <email>");
    expect(event.exception?.values?.[0]?.value).toBe("phone <phone>");
    expect(JSON.stringify(event)).not.toContain("ana");
  });

  it("drops query strings from navigation and fetch breadcrumbs", () => {
    const crumb = scrubBreadcrumb({
      category: "fetch",
      message: "GET ana@example.com",
      data: { url: "https://api.x.com/leads?q=ana", status_code: 500 },
    });

    expect(crumb.data).toEqual({ url: "https://api.x.com/leads", status_code: 500 });
    expect(crumb.message).toBe("GET <email>");
  });
});

describe("initSentry", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is off without a DSN, and then reports nothing", () => {
    expect(initSentry({ dsn: "", release: "abc", environment: "production", area: "panel" })).toBe(
      false,
    );
    reportServerError({ status: 500, method: "GET", path: "/leads", requestId: "r1" });

    expect(sentry.init).not.toHaveBeenCalled();
    expect(sentry.captureMessage).not.toHaveBeenCalled();
  });

  it("starts without replay or tracing, tagged with the area", () => {
    expect(
      initSentry({ dsn: "https://k@o1.ingest.sentry.io/1", release: "abc", environment: "", area: "backoffice" }),
    ).toBe(true);

    const options = sentry.init.mock.calls[0]![0];
    expect(options).toMatchObject({
      release: "abc",
      environment: "production",
      dataCollection: expect.objectContaining({ userInfo: false, httpBodies: [] }),
      tracesSampleRate: 0,
      initialScope: { tags: { area: "backoffice" } },
    });
    const kept = options.integrations([{ name: "Replay" }, { name: "GlobalHandlers" }]);
    expect(kept).toEqual([{ name: "GlobalHandlers" }]);
  });

  it("reports a 5xx with its request id and identifies by profile id only", () => {
    initSentry({ dsn: "https://k@o1.ingest.sentry.io/1", release: "", environment: "", area: "panel" });

    reportServerError({
      status: 502,
      method: "POST",
      path: "/leads/9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11/reply",
      requestId: "abc123",
    });
    identify("profile-1", "tenant-1");

    expect(sentry.captureMessage).toHaveBeenCalledWith(
      "API 502 POST /leads/9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11/reply",
      expect.objectContaining({
        tags: { request_id: "abc123", status: "502" },
        fingerprint: ["api-5xx", "POST", "/leads/:id/reply"],
      }),
    );
    expect(sentry.setUser).toHaveBeenCalledWith({ id: "profile-1" });
    expect(sentry.setTag).toHaveBeenCalledWith("tenant_id", "tenant-1");
  });
});
