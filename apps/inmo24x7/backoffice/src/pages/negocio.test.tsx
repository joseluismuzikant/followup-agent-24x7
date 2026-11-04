import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchBusiness,
  reactivateBusiness,
  retrySignup,
  sendReconnectLink,
  suspendBusiness,
} from "../api/backoffice";
import { businessDetail } from "../test-fixtures";
import { NegocioPage } from "./negocio";

vi.mock("../api/backoffice", () => ({
  fetchBusiness: vi.fn(),
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
