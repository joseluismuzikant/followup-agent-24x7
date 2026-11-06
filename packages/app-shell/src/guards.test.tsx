import type { SupabaseClient } from "@supabase/supabase-js";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PanelLayout } from "@followup/ui";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { AccountApi } from "./account";
import { ApiRequestError } from "./api";
import type { MeLike } from "./RequireProfile";
import { RequireAdmin } from "./RequireAdmin";
import { RequireProfile } from "./RequireProfile";

const session = { session: { accessToken: "t", email: "ana@example.com" }, loading: false, signOut: vi.fn() };
const useAuth = () => session;

function accountApi(mustChange = false): AccountApi {
  return {
    fetchAccount: vi.fn().mockResolvedValue({
      email: "ana@example.com",
      must_change_password: mustChange,
    }),
    changePassword: vi.fn(),
    fetchInvitation: vi.fn(),
    acceptInvitation: vi.fn(),
    devSignIn: vi.fn(),
  };
}

function me(isAdmin: boolean): MeLike {
  return {
    profile: { id: "p1", role: "owner", email: "ana@example.com", is_platform_admin: isAdmin },
    tenant: { id: "t1", status: "active" },
    support_email: "soporte@example.com",
  };
}

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={children} />
          <Route path="/onboarding" element={<p>Alta</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireProfile", () => {
  it("sends someone without a business in this product to the wizard", async () => {
    const fetchMe = vi.fn().mockRejectedValue(new ApiRequestError(404, "profile_not_found"));
    wrap(
      <RequireProfile fetchMe={fetchMe} useAuth={useAuth as never}>
        <p>Panel</p>
      </RequireProfile>,
    );

    expect(await screen.findByText("Alta")).toBeTruthy();
  });
});

describe("RequireAdmin", () => {
  const getSupabase = () => ({}) as SupabaseClient;

  it("names the product when the account has none in it", async () => {
    const fetchMe = vi.fn().mockRejectedValue(new ApiRequestError(404, "profile_not_found"));
    wrap(
      <RequireAdmin
        productName="Cuentas Claras"
        fetchMe={fetchMe}
        account={accountApi()}
        authMode="dev"
        getSupabase={getSupabase}
        useAuth={useAuth as never}
      >
        <p>Negocios</p>
      </RequireAdmin>,
    );

    expect(
      await screen.findByText(
        "Este usuario no tiene una cuenta en Cuentas Claras. Pedile acceso a un administrador.",
      ),
    ).toBeTruthy();
  });

  it("lets platform admins in", async () => {
    wrap(
      <RequireAdmin
        productName="Cuentas Claras"
        fetchMe={vi.fn().mockResolvedValue(me(true))}
        account={accountApi()}
        authMode="dev"
        getSupabase={getSupabase}
        useAuth={useAuth as never}
      >
        <p>Negocios</p>
      </RequireAdmin>,
    );

    expect(await screen.findByText("Negocios")).toBeTruthy();
  });

  it("asks for a new password before anything else", async () => {
    const fetchMe = vi.fn().mockResolvedValue(me(true));
    wrap(
      <RequireAdmin
        productName="Cuentas Claras"
        fetchMe={fetchMe}
        account={accountApi(true)}
        authMode="dev"
        getSupabase={getSupabase}
        useAuth={useAuth as never}
      >
        <p>Negocios</p>
      </RequireAdmin>,
    );

    expect(await screen.findByText("Elegí tu clave")).toBeTruthy();
    expect(screen.queryByText("Negocios")).toBeNull();
    expect(fetchMe).not.toHaveBeenCalled();
  });

  it("puts the admin's email and Cerrar sesión in the sidebar", async () => {
    wrap(
      <RequireAdmin
        productName="Cuentas Claras"
        fetchMe={vi.fn().mockResolvedValue(me(true))}
        account={accountApi()}
        authMode="dev"
        getSupabase={getSupabase}
        useAuth={useAuth as never}
      >
        <PanelLayout productName="Cuentas Claras" areaName="Backoffice" title="Negocios" navItems={[]}>
          <p>Lista</p>
        </PanelLayout>
      </RequireAdmin>,
    );

    expect(await screen.findByText("ana@example.com")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(session.signOut).toHaveBeenCalled();
  });
});
