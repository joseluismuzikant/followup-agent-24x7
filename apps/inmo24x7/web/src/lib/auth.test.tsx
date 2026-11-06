import { render, screen } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { readAuthMode } from "./auth-mode";
import { AuthProvider, RequireAuth, useAuth } from "./auth";
import { readDevToken, signOutDev, storeDevToken } from "./dev-session";
import { getSupabase } from "./supabase";

const mode = vi.hoisted(() => ({ current: "supabase" as "supabase" | "dev" }));
const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("./auth-mode", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth-mode")>()),
  get authMode() {
    return mode.current;
  },
}));
vi.mock("./supabase", () => ({ getSupabase: vi.fn(() => ({ auth })) }));

function SignOut() {
  const { signOut } = useAuth();
  return (
    <button type="button" onClick={() => void signOut()}>
      Salir
    </button>
  );
}

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <Routes>
          <Route path="/ingreso" element={<div>Ingreso</div>} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>Inicio</div>
                <SignOut />
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("RequireAuth with Supabase", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mode.current = "supabase";
    auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  });

  it("redirects to /ingreso when there is no session", async () => {
    auth.getSession.mockResolvedValue({ data: { session: null } });

    renderGuard();

    expect(await screen.findByText("Ingreso")).toBeTruthy();
  });

  it("renders the protected screen when authenticated", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "token", user: { email: "a@b.co" } } },
    });

    renderGuard();

    expect(await screen.findByText("Inicio")).toBeTruthy();
  });
});

describe("RequireAuth in dev mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mode.current = "dev";
    signOutDev();
  });

  it("uses the dev token and never builds the Supabase client", async () => {
    storeDevToken("dev:dueno@inmobiliariasur.test");

    renderGuard();

    expect(await screen.findByText("Inicio")).toBeTruthy();
    expect(getSupabase).not.toHaveBeenCalled();
  });

  it("signing out clears the dev token and goes back to /ingreso", async () => {
    storeDevToken("dev:dueno@inmobiliariasur.test");
    renderGuard();

    const button = await screen.findByRole("button", { name: "Salir" });
    await act(async () => button.click());

    expect(await screen.findByText("Ingreso")).toBeTruthy();
    expect(readDevToken()).toBeNull();
  });

  it("redirects to /ingreso without a dev session", async () => {
    renderGuard();

    expect(await screen.findByText("Ingreso")).toBeTruthy();
  });
});

describe("readAuthMode", () => {
  it("treats empty and unknown values as Supabase", () => {
    expect(readAuthMode(undefined)).toBe("supabase");
    expect(readAuthMode("")).toBe("supabase");
    expect(readAuthMode("prod")).toBe("supabase");
    expect(readAuthMode(" dev ")).toBe("dev");
  });
});
