import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchBusiness, reactivateBusiness, suspendBusiness } from "../api/backoffice";
import { fetchAdminReminders, planReminders, whatsappAdminApi } from "../api/reminders";
import { businessDetail } from "../test-fixtures";
import { NegocioPage } from "./negocio";

vi.mock("../api/backoffice", () => ({
  fetchBusiness: vi.fn(),
  suspendBusiness: vi.fn(),
  reactivateBusiness: vi.fn(),
}));
vi.mock("../api/reminders", () => ({
  fetchAdminReminders: vi.fn(),
  planReminders: vi.fn(),
  syncTemplates: vi.fn(),
  whatsappAdminApi: {
    fetchConnection: vi.fn(),
    saveConnection: vi.fn(),
    runConnectionAction: vi.fn(),
    sendTestMessage: vi.fn(),
  },
}));
vi.mock("../components/RequireAdmin", () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/negocios/33333333-3333-3333-3333-333333333333"]}>
        <Routes>
          <Route path="/negocios/:tenantId" element={<NegocioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Detalle del negocio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBusiness).mockResolvedValue(businessDetail());
    vi.mocked(whatsappAdminApi.fetchConnection).mockResolvedValue({
      status: "connected",
      display_phone_number: "+54 9 11 5555-0200",
      sender: "log",
      has_access_token: true,
    });
    vi.mocked(fetchAdminReminders).mockResolvedValue({
      templates: [
        {
          kind: "before",
          version: 1,
          name: "cuentas_claras_antes_v1",
          status: "approved",
          meta_status: "APPROVED",
          status_label: "aprobada",
          rejection_reason: null,
          meta_template_id: "tpl-1",
          last_synced_at: null,
        },
        {
          kind: "after",
          version: 1,
          name: "cuentas_claras_vencida_v1",
          status: "paused",
          meta_status: "PAUSED",
          status_label: "pausada por Meta",
          rejection_reason: null,
          meta_template_id: "tpl-3",
          last_synced_at: null,
        },
      ],
      errors: [
        {
          at: "2026-11-16T13:00:00Z",
          day: "2026-11-16",
          outcome: "skipped",
          reason: "template_not_approved:after",
          reason_label: "La plantilla no está aprobada",
          invoice_id: null,
          client_id: "c1",
        },
      ],
      month_count: 12,
      configured: true,
    });
  });

  it("shows the plan, owner, checklist, portfolio and activity", async () => {
    renderPage();

    expect(await screen.findByText("Dueño: dueno@ascensoresdelta.test")).toBeTruthy();
    expect(screen.getByText("Prueba · 12 días")).toBeTruthy();
    expect(screen.getByText("Configuración · 2 de 5")).toBeTruthy();
    expect(screen.getByText("Facturas cargadas")).toBeTruthy();
    expect(screen.getByText("Mercado Pago conectado")).toBeTruthy();
    expect(screen.getByText(/5\.400\.000/)).toBeTruthy();
    expect(screen.getByText("Importó facturas · 40 nuevas, 0 actualizadas, 0 con errores")).toBeTruthy();
    expect(screen.getByText("Marcó una factura como pagada · transferencia")).toBeTruthy();
  });

  it("suspends with a reason", async () => {
    vi.mocked(suspendBusiness).mockResolvedValue(
      businessDetail({ status: "suspended", suspended_reason: "Falta de pago" }),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Suspender" }));
    const dialog = screen.getByRole("dialog", { name: "Suspender Ascensores Delta" });
    const submit = within(dialog).getByRole("button", { name: "Suspender" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await user.type(within(dialog).getByLabelText("Motivo"), "Falta de pago");
    await user.click(submit);

    expect(suspendBusiness).toHaveBeenCalledWith(
      "33333333-3333-3333-3333-333333333333",
      "Falta de pago",
    );
    expect(await screen.findByText("Motivo: Falta de pago")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reactivar" })).toBeTruthy();
  });

  it("reactivates a suspended business", async () => {
    vi.mocked(fetchBusiness).mockResolvedValue(
      businessDetail({ status: "suspended", suspended_reason: "Falta de pago" }),
    );
    vi.mocked(reactivateBusiness).mockResolvedValue(businessDetail());
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Reactivar" }));

    expect(reactivateBusiness).toHaveBeenCalledWith("33333333-3333-3333-3333-333333333333");
    expect(await screen.findByRole("button", { name: "Suspender" })).toBeTruthy();
  });

  it("shows the reminders' templates and errors, and plans now", async () => {
    vi.mocked(planReminders).mockResolvedValue({
      sends: 3,
      escalated: 1,
      promises_ended: 0,
      paused: null,
    });
    const user = renderPage();

    const templates = await screen.findByRole("region", { name: "Plantillas" });
    expect(within(templates).getByText("pausada por Meta")).toBeTruthy();
    expect(screen.getByText(/No salió: La plantilla no está aprobada/)).toBeTruthy();
    expect(screen.getByText("12 enviados este mes")).toBeTruthy();
    expect(await screen.findByText("Solo log (desarrollo)")).toBeTruthy();
    expect(screen.queryByText("Plantilla de confirmación de visita")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Planificar ahora" }));

    expect(planReminders).toHaveBeenCalledWith("33333333-3333-3333-3333-333333333333");
    expect(
      await screen.findByText("Listo: 3 envíos programados, 1 escalados al dueño."),
    ).toBeTruthy();
  });
});
