import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAgentSetup, saveAgentSetup } from "../api/agent-setup";
import { fetchMe } from "../api/me";
import { advanceOnboarding, fetchOnboarding } from "../api/onboarding";
import { fetchSimulator } from "../api/simulator";
import { isOnboardingDeferred, resumeOnboarding } from "../lib/onboarding-deferred";
import { agentSetup, me, onboardingState, simulatorState } from "../test-fixtures";
import { OnboardingPage } from "./onboarding";

vi.mock("../api/me", () => ({ fetchMe: vi.fn(), signUp: vi.fn() }));
vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn(), advanceOnboarding: vi.fn() }));
vi.mock("../api/agent-setup", () => ({ fetchAgentSetup: vi.fn(), saveAgentSetup: vi.fn() }));
vi.mock("../api/simulator", () => ({
  fetchSimulator: vi.fn(),
  sendSimulatorMessage: vi.fn(),
  resetSimulator: vi.fn(),
}));
vi.mock("../api/tenant-settings", () => ({
  fetchTenantSettings: vi.fn(),
  saveTenantSettings: vi.fn(),
}));

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderWizard(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/onboarding/:step?" element={<><OnboardingPage /><Where /></>} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const where = () => screen.getByTestId("where").textContent;

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resumeOnboarding();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchAgentSetup).mockResolvedValue(agentSetup());
    vi.mocked(fetchSimulator).mockResolvedValue(simulatorState());
  });

  it("resumes at the saved step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));

    renderWizard("/onboarding");

    expect(await screen.findByText("Escribile como si fueras un cliente")).toBeTruthy();
    expect(where()).toBe("/onboarding/probalo");
    expect(screen.getByText(/Paso 3 de 5 · Probalo/)).toBeTruthy();
    expect(
      screen.getByText(
        "Así va a responder en WhatsApp. Todavía no conectaste nada: esto es una prueba privada.",
      ),
    ).toBeTruthy();
    expect(await screen.findByLabelText("Mensaje")).toBeTruthy();
    expect(screen.getByRole("button", { name: "← Ajustar el agente" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Me gusta, conectar WhatsApp" })).toBeTruthy();
  });

  it("sends deep links to future steps back to the saved step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("agent"));

    renderWizard("/onboarding/whatsapp");

    expect(await screen.findByLabelText("Nombre del agente")).toBeTruthy();
    expect(where()).toBe("/onboarding/tu-agente");
  });

  it("explains the three WhatsApp steps with the S4 copy", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("whatsapp"));

    renderWizard("/onboarding/whatsapp");

    expect(
      await screen.findByText(
        "Se abre una ventana de Meta. Tarda unos 3 minutos y no necesitás saber nada técnico.",
      ),
    ).toBeTruthy();
    for (const title of [
      "Entrá con tu cuenta de Facebook",
      "Elegí el número",
      "Confirmá con el código por SMS",
    ]) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    expect(screen.queryByRole("button", { name: "Conectar WhatsApp" })).toBeNull();
  });

  it("lets the stepper jump to completed steps only", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderWizard("/onboarding/probalo");
    await screen.findByText("Escribile como si fueras un cliente");

    expect((screen.getByRole("button", { name: "WhatsApp" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: /Tu agente/ }));

    expect(await screen.findByLabelText("Nombre del agente")).toBeTruthy();
    expect(where()).toBe("/onboarding/tu-agente");
    // Going back never moves the saved step.
    expect(advanceOnboarding).not.toHaveBeenCalled();
  });

  it("saves the agent and advances to Probalo", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("agent"));
    vi.mocked(saveAgentSetup).mockResolvedValue(agentSetup({ version: 1 }));
    vi.mocked(advanceOnboarding).mockImplementation(async () => {
      vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
      return onboardingState("try");
    });
    renderWizard("/onboarding/tu-agente");

    await user.click(await screen.findByRole("button", { name: "Guardar y probar mi agente" }));

    expect(saveAgentSetup).toHaveBeenCalledTimes(1);
    expect(advanceOnboarding).toHaveBeenCalledWith("try");
    expect(await screen.findByText("Escribile como si fueras un cliente")).toBeTruthy();
  });

  it("Terminar después goes to the panel for this session", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderWizard("/onboarding/probalo");

    await user.click(await screen.findByRole("button", { name: "Terminar después" }));

    expect(where()).toBe("/");
    expect(isOnboardingDeferred()).toBe(true);
  });

  it("starts at step 1 without Terminar después when there is no profile yet", async () => {
    vi.mocked(fetchMe).mockRejectedValue(new ApiRequestError(404, "profile_not_found"));

    renderWizard("/onboarding");

    expect(await screen.findByLabelText("Nombre del negocio")).toBeTruthy();
    expect(screen.getByText(/Paso 1 de 5/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Terminar después" })).toBeNull();
  });

  it("shows what is ready and pending on the last step", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));

    renderWizard("/onboarding/listo");

    expect(await screen.findByText("✓ Cuenta creada")).toBeTruthy();
    expect(screen.getByText("Propiedades cargadas")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ir a mi panel" })).toBeTruthy();
  });
});
