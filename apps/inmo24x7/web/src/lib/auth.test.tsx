import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, RequireAuth } from "./auth";
import { supabase } from "./supabase";

vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

const getSession = vi.mocked(supabase.auth.getSession);
const onAuthStateChange = vi.mocked(supabase.auth.onAuthStateChange);

function renderGuard(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <Routes>
          <Route path="/ingreso" element={<div>Ingreso</div>} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>Inicio</div>
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: vi.fn() } },
    } as never);
  });

  it("redirects to /ingreso when there is no session", async () => {
    getSession.mockResolvedValue({ data: { session: null } } as never);

    renderGuard("/");

    expect(await screen.findByText("Ingreso")).toBeTruthy();
  });

  it("renders the protected screen when authenticated", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "token" } },
    } as never);

    renderGuard("/");

    expect(await screen.findByText("Inicio")).toBeTruthy();
  });
});
