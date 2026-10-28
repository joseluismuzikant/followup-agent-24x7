import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";
import { RequireProfile } from "./RequireProfile";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));

const fetchMeMock = vi.mocked(fetchMe);
const useAuthMock = vi.mocked(useAuth);
const signOut = vi.fn();

function renderGuard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/ingreso" element={<div>Ingreso</div>} />
          <Route path="/onboarding" element={<div>Onboarding</div>} />
          <Route
            path="/"
            element={
              <RequireProfile>
                <div>Panel</div>
              </RequireProfile>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireProfile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signOut.mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({
      session: { access_token: "token" },
      loading: false,
      signOut,
    } as never);
  });

  it("redirects to /onboarding when the profile does not exist", async () => {
    fetchMeMock.mockRejectedValue(new ApiRequestError(404, "profile_not_found"));

    renderGuard();

    expect(await screen.findByText("Onboarding")).toBeTruthy();
  });

  it("signs out and goes to /ingreso on 401", async () => {
    fetchMeMock.mockRejectedValue(new ApiRequestError(401, "unauthorized"));

    renderGuard();

    expect(await screen.findByText("Ingreso")).toBeTruthy();
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("shows an error card with retry and sign out on other errors", async () => {
    const user = userEvent.setup();
    fetchMeMock.mockRejectedValueOnce(new ApiRequestError(503, "database_unavailable"));

    renderGuard();

    expect(await screen.findByText("No pudimos cargar tu cuenta")).toBeTruthy();
    expect(screen.queryByText("Ingreso")).toBeNull();

    fetchMeMock.mockResolvedValue({} as never);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(screen.getByText("Panel")).toBeTruthy());
  });

  it("lets the user sign out from the error card", async () => {
    const user = userEvent.setup();
    fetchMeMock.mockRejectedValue(new ApiRequestError(500, "internal_error"));

    renderGuard();

    await user.click(await screen.findByRole("button", { name: "Cerrar sesión" }));
    expect(signOut).toHaveBeenCalled();
  });
});
