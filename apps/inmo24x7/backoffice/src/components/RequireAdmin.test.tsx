import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

function renderGuard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RequireAdmin>
          <p>Negocios</p>
        </RequireAdmin>
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
  });

  it("in dev mode shows the development box instead of Google and the magic link", async () => {
    mode.current = "dev";
    vi.mocked(fetchMe).mockResolvedValue({
      profile: { is_platform_admin: true },
    } as Awaited<ReturnType<typeof fetchMe>>);
    const user = renderGuard();

    expect(await screen.findByText("Modo desarrollo")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Continuar con Google" })).toBeNull();

    await user.type(screen.getByLabelText("Email de prueba"), "admin@local.test");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(readDevToken()).toBe("dev:admin@local.test");
    expect(await screen.findByText("Negocios")).toBeTruthy();
  });

  it("in Supabase mode shows Google and the magic link only", async () => {
    mode.current = "supabase";
    renderGuard();

    expect(await screen.findByRole("button", { name: "Continuar con Google" })).toBeTruthy();
    expect(screen.queryByText("Modo desarrollo")).toBeNull();
  });
});
