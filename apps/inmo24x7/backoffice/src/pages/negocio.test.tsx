import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchBusiness,
  fetchErrors,
  fetchSystemHealth,
  fetchTenantUsage,
  reactivateBusiness,
  retrySignup,
  sendReconnectLink,
  suspendBusiness,
} from "../api/backoffice";
import {
  businessDetail,
  errorList,
  sentryIssue,
  systemHealth,
  tenantUsage,
  usageFigures,
} from "../test-fixtures";
import { NegocioPage } from "./negocio";

vi.mock("../api/backoffice", () => ({
  fetchBusiness: vi.fn(),
  fetchErrors: vi.fn(),
  fetchSystemHealth: vi.fn(),
  fetchTenantUsage: vi.fn(),
  suspendBusiness: vi.fn(),
  reactivateBusiness: vi.fn(),
  sendReconnectLink: vi.fn(),
  retrySignup: vi.fn(),
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("../components/WhatsAppConnection", () => ({
  WhatsAppConnectionPanel: () => <p>Formulario manual</p>,
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/negocios/t1"]}>
        <Routes>
          <Route path="/negocios/:tenantId" element={<NegocioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Detalle del negocio (S9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBusiness).mockResolvedValue(businessDetail());
    vi.mocked(fetchErrors).mockResolvedValue(errorList({ issues: [] }));
    vi.mocked(fetchSystemHealth).mockResolvedValue(systemHealth());
    vi.mocked(fetchTenantUsage).mockResolvedValue(tenantUsage());
  });

  it("shows this business's errors, its logs link and this month's consumption", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(
      errorList({
        issues: Array.from({ length: 6 }, (_, index) =>
          sentryIssue({ id: String(index), title: `Error ${index}` }),
        ),
      }),
    );
    vi.mocked(fetchSystemHealth).mockResolvedValue(
      systemHealth({
        links: {
          grafana_url: "https://grafana.example.com",
          loki_datasource: "loki",
          sentry_issues_url: "https://acme.sentry.io/issues/",
        },
      }),
    );
    vi.mocked(fetchTenantUsage).mockResolvedValue(
      tenantUsage({ business: { ...tenantUsage().business, figures: usageFigures({ unpriced_calls: 2 }) } }),
    );
    renderPage();

    expect(await screen.findByText("Errores de este negocio (7 días) · 6")).toBeTruthy();
    expect(screen.getByText("Error 4")).toBeTruthy();
    expect(screen.queryByText("Error 5")).toBeNull();
    const id = businessDetail().id;
    expect(fetchErrors).toHaveBeenCalledWith({ period: "7d", tenantId: id, limit: 25 });
    const logs = screen.getByRole("link", { name: "Ver logs" }).getAttribute("href") ?? "";
    expect(logs.startsWith("https://grafana.example.com/explore?")).toBe(true);
    expect(decodeURIComponent(logs)).toContain(`| json | tenant_id=\\"${id}\\"`);

    expect(await screen.findByText("Consumo este mes")).toBeTruthy();
    expect(screen.getByText(/Costo del LLM/).textContent).toContain("0,49");
    expect(screen.getByText("sin precio")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ver el detalle" }).getAttribute("href")).toMatch(
      new RegExp(`^/consumo\\?negocio=${id}&mes=\\d{4}-\\d{2}$`),
    );
  });

  it("hides the logs link without Grafana and explains an unconfigured Sentry", async () => {
    vi.mocked(fetchErrors).mockResolvedValue(errorList({ configured: false, available: false, issues: [] }));
    renderPage();

    expect(await screen.findByText(/Sentry no está configurado/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Ver logs" })).toBeNull();
  });

  it("shows the WhatsApp diagnosis with the masked WABA and the Meta code", async () => {
    const user = renderPage();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("El permiso de Meta venció");
    expect(alert.textContent).toContain("El cliente quitó el acceso de la app en su cuenta de Meta.");
    expect(alert.textContent).toContain("Los mensajes fallan desde");
    expect(screen.getByText("•••• 4321")).toBeTruthy();
    expect(screen.getByText("En revisión")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Código de Meta: 190/ }));
    expect(screen.getByText(/Código interno: token_revoked/)).toBeTruthy();
  });

  it("shows activity, onboarding, plan usage and users", async () => {
    renderPage();

    expect(await screen.findByText("WhatsApp dejó de funcionar · código de Meta 190")).toBeTruthy();
    expect(screen.getByText("Importó propiedades · 12 nuevas, 0 actualizadas, 2 con errores")).toBeTruthy();
    expect(screen.getAllByText(/Sistema ·/)).toHaveLength(1);
    expect(screen.getByText("Onboarding · 3 de 5")).toBeTruthy();
    expect(screen.getByText("1.234 de 1.000")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Cambiar plan · Próximamente" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(screen.getByText("Dueño")).toBeTruthy();
    expect(screen.getByText("Agente")).toBeTruthy();
  });

  it("sends the reconnect link, retries the signup and opens the manual form", async () => {
    vi.mocked(sendReconnectLink).mockResolvedValue(1);
    vi.mocked(retrySignup).mockResolvedValue({} as never);
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Enviarle link para reconectar" }));
    expect(await screen.findByText("Le mandamos el link al dueño.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reintentar configuración" }));
    expect(retrySignup).toHaveBeenCalledWith(businessDetail().id);
    await user.click(screen.getByRole("button", { name: "Conexión manual y mensaje de prueba" }));
    expect(screen.getByText("Formulario manual")).toBeTruthy();
  });

  it("suspends with a reason and reactivates", async () => {
    const suspended = businessDetail({ status: "suspended", suspended_reason: "Falta de pago" });
    vi.mocked(suspendBusiness).mockResolvedValue(suspended);
    vi.mocked(reactivateBusiness).mockResolvedValue(businessDetail());
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Suspender" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta de pago");
    await user.click(within(dialog).getByRole("button", { name: "Suspender" }));

    expect(suspendBusiness).toHaveBeenCalledWith(businessDetail().id, "Falta de pago");
    expect(await screen.findByText("Motivo: Falta de pago")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reactivar" }));
    expect(reactivateBusiness).toHaveBeenCalled();
  });
});
