import type { WhatsAppStatus } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  SignupRequestError,
  completeEmbeddedSignup,
  reportSignupAbandoned,
  retryEmbeddedSignup,
} from "../../api/whatsapp";
import { whatsappStatus } from "../../test-fixtures";
import { ConnectWhatsApp } from "./ConnectWhatsApp";

vi.mock("../../api/whatsapp", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/whatsapp")>();
  return {
    ...actual,
    completeEmbeddedSignup: vi.fn(),
    retryEmbeddedSignup: vi.fn(),
    reportSignupAbandoned: vi.fn(),
  };
});

const connected = whatsappStatus({
  status: "connected",
  display_phone_number: "+54 9 11 5555-0100",
  verified_name: "Inmo Sur",
  business_verification: "unknown",
});

let loginCallback: ((response: { authResponse?: { code?: string } | null }) => void) | null;
const login = vi.fn();

function renderConnect(status: WhatsAppStatus = whatsappStatus()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConnectWhatsApp status={status} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

function metaMessage(event: string, data: Record<string, string> = {}) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        origin: "https://www.facebook.com",
        data: JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event, data }),
      }),
    );
  });
}

describe("ConnectWhatsApp (S4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("VITE_META_APP_ID", "app-123");
    vi.stubEnv("VITE_META_EMBEDDED_SIGNUP_CONFIG_ID", "config-456");
    loginCallback = null;
    login.mockImplementation((callback) => {
      loginCallback = callback;
    });
    window.FB = { init: vi.fn(), login };
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.FB;
  });

  it("opens Meta's popup with the Embedded Signup configuration", async () => {
    const user = renderConnect();

    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    expect(login).toHaveBeenCalledWith(expect.any(Function), {
      config_id: "config-456",
      response_type: "code",
      override_default_response_type: true,
      extras: { setup: {} },
    });
    expect(screen.getByRole("button", { name: "Esperando a Meta..." })).toBeTruthy();
  });

  it("sends the code and the ids together and shows the connected number", async () => {
    vi.mocked(completeEmbeddedSignup).mockResolvedValue(connected);
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    metaMessage("FINISH", { phone_number_id: "pn-1", waba_id: "waba-1", business_id: "biz-1" });
    act(() => loginCallback?.({ authResponse: { code: "code-30s" } }));

    await screen.findByText("+54 9 11 5555-0100 · Inmo Sur");
    expect(completeEmbeddedSignup).toHaveBeenCalledWith({
      code: "code-30s",
      waba_id: "waba-1",
      phone_number_id: "pn-1",
      business_id: "biz-1",
    });
    // Business verification unknown: both Meta links with neutral copy.
    expect(screen.getByRole("link", { name: "Verificar tu empresa" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Cargar un medio de pago" })).toBeTruthy();
  });

  it("ignores messages from other origins", async () => {
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          origin: "https://evilfacebook.com",
          data: JSON.stringify({ type: "WA_EMBEDDED_SIGNUP", event: "CANCEL", data: {} }),
        }),
      );
    });

    expect(reportSignupAbandoned).not.toHaveBeenCalled();
  });

  it("records a cancel with the step and explains it in Spanish", async () => {
    vi.mocked(reportSignupAbandoned).mockResolvedValue(null);
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    metaMessage("CANCEL", { current_step: "PHONE_NUMBER_SETUP" });

    expect(await screen.findByText(/Cerraste la ventana de Meta antes de terminar/)).toBeTruthy();
    expect(reportSignupAbandoned).toHaveBeenCalledWith({
      event: "CANCEL",
      current_step: "PHONE_NUMBER_SETUP",
      error_code: null,
    });
  });

  it("shows Meta's error translated by the API", async () => {
    vi.mocked(reportSignupAbandoned).mockResolvedValue({
      code: "number_in_other_account",
      title: "Ese número ya está en otra cuenta",
      message: "Ese número ya está registrado en otra cuenta.",
      action: "Eliminá el número de la otra cuenta o elegí otro.",
    });
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    metaMessage("ERROR", { error_code: "2388012", error_message: "x" });

    expect(await screen.findByText("Ese número ya está en otra cuenta")).toBeTruthy();
  });

  it("says the number is missing when Meta finished without one", async () => {
    vi.mocked(reportSignupAbandoned).mockResolvedValue(null);
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));

    metaMessage("FINISH_ONLY_WABA", { waba_id: "waba-1" });

    expect(await screen.findByText("Falta elegir el número")).toBeTruthy();
    expect(completeEmbeddedSignup).not.toHaveBeenCalled();
  });

  it("offers to retry a failed step and resumes it", async () => {
    vi.mocked(completeEmbeddedSignup).mockRejectedValue(
      new SignupRequestError(502, "whatsapp_signup_failed", {
        code: "pin_mismatch",
        title: "El número tiene otro PIN",
        message: "El número ya tiene una verificación en dos pasos.",
        action: "Desactivala y volvé a intentar.",
      }),
    );
    vi.mocked(retryEmbeddedSignup).mockResolvedValue(connected);
    const user = renderConnect();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    act(() => loginCallback?.({ authResponse: { code: "code-30s" } }));
    metaMessage("FINISH", { phone_number_id: "pn-1", waba_id: "waba-1" });

    expect(await screen.findByText("El número tiene otro PIN")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reintentar configuración" }));

    await waitFor(() => expect(retryEmbeddedSignup).toHaveBeenCalled());
    expect(await screen.findByText("+54 9 11 5555-0100 · Inmo Sur")).toBeTruthy();
  });

  it("shows the error state with the translated message and Volver a conectar", () => {
    renderConnect(
      whatsappStatus({
        ...connected,
        status: "error",
        failing_since: new Date(Date.now() - 2 * 3600_000).toISOString(),
        error: {
          code: "token_revoked",
          title: "El permiso de Meta venció",
          message: "Tu agente no puede responder en WhatsApp.",
          action: "Tocá Volver a conectar.",
        },
      }),
    );

    expect(screen.getByRole("alert").textContent).toContain("El permiso de Meta venció");
    expect(screen.getByRole("alert").textContent).toContain("Los mensajes no salen desde hace 2 horas");
    expect(screen.getAllByRole("button", { name: "Volver a conectar" }).length).toBeGreaterThan(0);
  });

  it("is disabled without the Meta app configured", () => {
    vi.unstubAllEnvs();
    vi.stubEnv("VITE_META_APP_ID", "");
    renderConnect();

    const button = screen.getByRole("button", { name: "Conectar WhatsApp" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText(/no está configurada en este entorno/)).toBeTruthy();
  });
});
