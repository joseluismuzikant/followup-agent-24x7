import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { account } from "../api/client";
import { fetchMe } from "../api/me";
import { AuthProvider } from "../lib/auth";
import { readDevToken, signOutDev } from "../lib/dev-session";
import { RequireAdmin } from "./RequireAdmin";

const mode = vi.hoisted(() => ({ current: "dev" as "supabase" | "dev" }));
const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("../lib/auth-mode", () => ({
  get authMode() {
    return mode.current;
  },
}));
vi.mock("../lib/supabase", () => ({ getSupabase: vi.fn(() => ({ auth })) }));
vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/client", () => ({ account: { fetchAccount: vi.fn(), devSignIn: vi.fn() } }));

function renderGuard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter>
          <RequireAdmin>
            <p>Negocios</p>
          </RequireAdmin>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("RequireAdmin sign-in", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signOutDev();
    auth.getSession.mockResolvedValue({ data: { session: null } });
    auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
    vi.mocked(account.fetchAccount).mockResolvedValue({
      email: "admin@local.test",
      must_change_password: false,
    });
  });

  it("in dev mode checks the password with the API and lets the admin in", async () => {
    mode.current = "dev";
    vi.mocked(fetchMe).mockResolvedValue({
      profile: { is_platform_admin: true },
    } as Awaited<ReturnType<typeof fetchMe>>);
    vi.mocked(account.devSignIn).mockResolvedValue("dev:admin@local.test");
    const user = renderGuard();

    expect(await screen.findByText("Entrá al backoffice")).toBeTruthy();
    await user.type(screen.getByLabelText("Email"), "admin@local.test");
    await user.type(screen.getByLabelText("Clave"), "local-1234");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(account.devSignIn).toHaveBeenCalledWith("admin@local.test", "local-1234");
    expect(readDevToken()).toBe("dev:admin@local.test");
    expect(await screen.findByText("Negocios")).toBeTruthy();
  });

  it("asks an admin with a temporary password to choose one first", async () => {
    mode.current = "dev";
    vi.mocked(account.fetchAccount).mockResolvedValue({
      email: "admin@local.test",
      must_change_password: true,
    });
    const { storeDevToken } = await import("../lib/dev-session");
    storeDevToken("dev:admin@local.test");
    renderGuard();

    expect(await screen.findByText("Elegí tu clave")).toBeTruthy();
    expect(screen.queryByText("Negocios")).toBeNull();
  });

  it("in Supabase mode has no development hint", async () => {
    mode.current = "supabase";
    renderGuard();

    expect(await screen.findByLabelText("Clave")).toBeTruthy();
    expect(screen.queryByText(/Modo desarrollo/)).toBeNull();
  });

  describe("when signed in", () => {
    beforeEach(() => {
      mode.current = "dev";
    });

    async function signedIn(email = "persona@local.test") {
      const { storeDevToken } = await import("../lib/dev-session");
      storeDevToken(`dev:${email}`);
      return renderGuard();
    }

    it("tells a non-admin who they are and lets them sign out", async () => {
      vi.mocked(fetchMe).mockResolvedValue({
        profile: { is_platform_admin: false, email: "persona@local.test" },
      } as Awaited<ReturnType<typeof fetchMe>>);
      const user = await signedIn();

      expect(await screen.findByText("Solo administradores de la plataforma.")).toBeTruthy();
      expect(screen.getByText("persona@local.test")).toBeTruthy();
      await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));
      expect(readDevToken()).toBeNull();
    });

    it.each([
      [new ApiRequestError(401, "unauthorized"), "Tu sesión no es válida o venció"],
      [new ApiRequestError(404, "profile_not_found"), "no tiene una cuenta en inmo24x7"],
      [new TypeError("Failed to fetch"), "No pudimos conectarnos con el servidor"],
    ])("shows an error card with Reintentar and Cerrar sesión (%s)", async (error, message) => {
      vi.mocked(fetchMe).mockRejectedValueOnce(error);
      const user = await signedIn();

      expect((await screen.findByRole("alert")).textContent).toContain(message);
      expect(screen.queryByText("Solo administradores de la plataforma.")).toBeNull();
      expect(screen.getByText("persona@local.test")).toBeTruthy();

      vi.mocked(fetchMe).mockResolvedValue({
        profile: { is_platform_admin: true, email: "persona@local.test" },
      } as Awaited<ReturnType<typeof fetchMe>>);
      await user.click(screen.getByRole("button", { name: "Reintentar" }));
      expect(await screen.findByText("Negocios")).toBeTruthy();
    });
  });
});
