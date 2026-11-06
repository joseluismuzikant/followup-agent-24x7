import { ApiRequestError } from "@followup/api-client-cuentas-claras";
import { isOnboardingDeferred, resumeOnboarding } from "@followup/app-shell";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe, signUp } from "../api/me";
import { advanceOnboarding, fetchOnboarding } from "../api/onboarding";
import { me, onboardingState } from "../test-fixtures";
import { OnboardingPage } from "./onboarding";

vi.mock("../api/me", () => ({ fetchMe: vi.fn(), signUp: vi.fn() }));
vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn(), advanceOnboarding: vi.fn() }));
vi.mock("../api/tenant-settings", () => ({
  fetchTenantSettings: vi.fn(),
  saveTenantSettings: vi.fn(),
}));
vi.mock("../api/invoices", () => ({
  importInvoices: vi.fn(),
  downloadImportErrors: vi.fn(),
  downloadImportTemplate: vi.fn(),
}));

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderWizard(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/onboarding/:step?"
            element={
              <>
                <OnboardingPage />
                <Where />
              </>
            }
          />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

const where = () => screen.getByTestId("where").textContent;

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resumeOnboarding();
    vi.mocked(fetchMe).mockResolvedValue(me());
  });

  it("joins the invited business and lands on Tus facturas", async () => {
    // No profile until the first sign-in joins the business the admin created.
    vi.mocked(fetchMe).mockRejectedValueOnce(new ApiRequestError(404, "profile_not_found"));
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("invoices"));
    vi.mocked(signUp).mockResolvedValue({} as Awaited<ReturnType<typeof signUp>>);
    renderWizard("/onboarding");

    expect(await screen.findByText("Cuentas Claras · Paso 2 de 5 · Tus facturas")).toBeTruthy();
    expect(signUp).toHaveBeenCalledTimes(1);
    expect(where()).toBe("/onboarding/tus-facturas");
  });

  it("tells an email nobody invited that it is not enabled", async () => {
    vi.mocked(fetchMe).mockRejectedValue(new ApiRequestError(404, "profile_not_found"));
    vi.mocked(signUp).mockRejectedValue(new ApiRequestError(403, "not_invited"));
    renderWizard("/onboarding");

    expect(await screen.findByText("Tu cuenta no está habilitada")).toBeTruthy();
  });

  it("resumes at the saved step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("reminders"));
    renderWizard("/onboarding");

    expect(await screen.findByText("Así vamos a recordarles a tus clientes")).toBeTruthy();
    expect(where()).toBe("/onboarding/recordatorios");
    expect(screen.getByText("Muy pronto vas a poder ajustarla.")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Secuencia de recordatorios" }).children).toHaveLength(4);
  });

  it("does not jump ahead of the saved step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("invoices"));
    renderWizard("/onboarding/listo");

    expect(await screen.findByText("Cuentas Claras · Paso 2 de 5 · Tus facturas")).toBeTruthy();
    expect(where()).toBe("/onboarding/tus-facturas");
  });

  it("lets the invoices wait with Cargar después", async () => {
    vi.mocked(fetchOnboarding)
      .mockResolvedValueOnce(onboardingState("invoices"))
      .mockResolvedValue(onboardingState("reminders"));
    vi.mocked(advanceOnboarding).mockResolvedValue(onboardingState("reminders"));
    const user = renderWizard("/onboarding/tus-facturas");

    expect(await screen.findByText("Descargar la plantilla")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Cargar después" }));

    expect(advanceOnboarding).toHaveBeenCalledWith("reminders");
    expect(await screen.findByText("Así vamos a recordarles a tus clientes")).toBeTruthy();
    expect(where()).toBe("/onboarding/recordatorios");
  });

  it("shows WhatsApp and Mercado Pago as coming soon", async () => {
    vi.mocked(fetchOnboarding)
      .mockResolvedValueOnce(onboardingState("connect"))
      .mockResolvedValue(onboardingState("done"));
    vi.mocked(advanceOnboarding).mockResolvedValue(onboardingState("done"));
    const user = renderWizard("/onboarding/conectar");

    expect(await screen.findByRole("region", { name: "WhatsApp" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Mercado Pago" })).toBeTruthy();
    expect(screen.getAllByText("Muy pronto")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Seguir" }));
    expect(await screen.findByText("¡Listo!")).toBeTruthy();
    expect(where()).toBe("/onboarding/listo");
  });

  it("finishes later from any step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("reminders"));
    const user = renderWizard("/onboarding/recordatorios");

    await user.click(await screen.findByRole("button", { name: "Terminar después" }));

    expect(isOnboardingDeferred()).toBe(true);
    expect(where()).toBe("/");
  });

  it("lists what is ready and what is pending at the end", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done", { invoicesLoaded: true }));
    const user = renderWizard("/onboarding/listo");

    expect(await screen.findByText("✓ Cargar tus facturas")).toBeTruthy();
    expect(screen.getByText("Conectar Mercado Pago (muy pronto)")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Ir a mi panel" }));
    expect(where()).toBe("/");
  });
});
