import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchErrors, fetchSystemHealth, triggerApiTestError } from "../api/backoffice";
import { errorList, systemHealth } from "../test-fixtures";
import { ErroresPage } from "./errores";

vi.mock("../api/backoffice", () => ({
  fetchErrors: vi.fn(),
  fetchSystemHealth: vi.fn(),
  triggerApiTestError: vi.fn(),
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

const links = {
  grafana_url: "https://grafana.example.com",
  loki_datasource: "loki",
  sentry_issues_url: "https://acme.sentry.io/issues/",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ErroresPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Errores", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth({ links }));
  });

  it("lists open issues linking to Sentry and filters by project and period", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(errorList());
    const user = renderPage();

    expect(await screen.findByRole("link", { name: "TypeError: x" })).toBeTruthy();
    expect(screen.getAllByText("Panel").length).toBeGreaterThan(1); // the filter and the badge
    expect(fetchErrors).toHaveBeenLastCalledWith({ project: "all", period: "24h", limit: 50 });

    await user.click(screen.getByRole("radio", { name: "API y worker" }));
    await user.click(screen.getByRole("radio", { name: "7 días" }));

    expect(fetchErrors).toHaveBeenLastCalledWith({ project: "api", period: "7d", limit: 50 });
  });

  it("explains an unconfigured Sentry", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(
      errorList({ configured: false, available: false, issues: [], sentry_issues_url: "" }),
    );
    renderPage();

    expect((await screen.findByRole("status")).textContent).toContain("Sentry no está configurado");
    expect(screen.queryByRole("link", { name: "Ver todos en Sentry" })).toBeNull();
  });

  it("says when Sentry is unavailable and keeps the link to it", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(errorList({ available: false, issues: [] }));
    renderPage();

    expect((await screen.findByRole("status")).textContent).toContain("Sentry no respondió");
    expect(screen.getByRole("link", { name: "Ver todos en Sentry" })).toBeTruthy();
  });

  it("opens a reference code's logs in Grafana and its errors in Sentry", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(errorList());
    const user = renderPage();

    await user.type(await screen.findByLabelText("Código de referencia"), " 1A2B3C4D ");

    const logs = screen.getByRole("link", { name: "Ver logs en Grafana" }).getAttribute("href") ?? "";
    const panes = JSON.parse(decodeURIComponent(logs.split("panes=")[1] ?? ""));
    expect(logs.startsWith("https://grafana.example.com/explore?")).toBe(true);
    expect(panes.a.queries[0].expr).toBe('{environment="production"} | json | request_id=~"1a2b3c4d.*"');
    expect(panes.a.datasource).toBe("loki");
    expect(screen.getByRole("link", { name: "Buscar en Sentry" }).getAttribute("href")).toBe(
      "https://acme.sentry.io/issues/?query=request_id%3A1a2b3c4d*&statsPeriod=14d",
    );
  });

  it("hides the search links when nothing is configured", async () => {
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth());
    vi.mocked(fetchErrors).mockResolvedValue(errorList());
    const user = renderPage();

    await user.type(await screen.findByLabelText("Código de referencia"), "1a2b3c4d");

    expect(screen.queryByRole("link", { name: "Ver logs en Grafana" })).toBeNull();
    expect(screen.getByText(/Configurá GRAFANA_URL o SENTRY_ORG/)).toBeTruthy();
  });

  it("sends test errors and says where to find them", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(errorList());
    vi.mocked(triggerApiTestError).mockResolvedValue("1a2b3c4d");
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Enviar errores de prueba" }));

    const status = await screen.findByText(/Enviados\./);
    expect(status.textContent).toContain("código de referencia 1a2b3c4d");
    // Sentry is off in tests: the panel's own test error is not sent, and it says so.
    expect(status.textContent).toContain("no tiene VITE_SENTRY_DSN");
  });
});
