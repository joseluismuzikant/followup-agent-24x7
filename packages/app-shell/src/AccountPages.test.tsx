import type { SupabaseClient } from "@supabase/supabase-js";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AccountApi } from "./account";
import {
  ChangePasswordPage,
  ClaimInvitation,
  InvitationPage,
  RequireAccount,
} from "./AccountPages";
import { ApiRequestError } from "./api";
import { readDevToken, signOutDev } from "./auth/dev-session";

const signOut = vi.fn();
const session = { session: { accessToken: "t", email: "ana@example.com" }, loading: false, signOut };
const useAuth = (() => session) as never;
const getSupabase = () => ({}) as SupabaseClient;

const account = {
  fetchAccount: vi.fn(),
  changePassword: vi.fn(),
  fetchInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  devSignIn: vi.fn(),
} satisfies AccountApi;

function wrap(path: string, element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<p>Panel</p>} />
          <Route path="/cambiar-clave" element={<p>Cambiar clave</p>} />
          <Route path="/invitacion" element={element} />
          <Route path="/claim" element={element} />
          <Route path="/guarded" element={element} />
          <Route path="/clave" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const props = { productName: "inmo24x7", account, authMode: "dev" as const, getSupabase, useAuth };

async function choose(password: string, repeat = password, button = "Crear mi clave y entrar") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Clave nueva"), password);
  await user.type(screen.getByLabelText("Repetí la clave"), repeat);
  await user.click(screen.getByRole("button", { name: button }));
}

describe("InvitationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signOutDev();
  });

  it("creates the password and signs the invited person in", async () => {
    account.fetchInvitation.mockResolvedValue({
      email: "v@u.test",
      business_name: "Villa Urquiza",
      status: "valid",
      needs_password: true,
    });
    account.acceptInvitation.mockResolvedValue("v@u.test");
    account.devSignIn.mockResolvedValue("dev:v@u.test");
    wrap("/invitacion?token=abc", <InvitationPage {...props} />);

    expect(await screen.findByText("Villa Urquiza")).toBeTruthy();
    await choose("mi-clave-nueva");

    expect(account.acceptInvitation).toHaveBeenCalledWith("abc", "mi-clave-nueva");
    expect(await screen.findByText("Panel")).toBeTruthy();
    expect(readDevToken()).toBe("dev:v@u.test");
  });

  it("checks both passwords match before calling the API", async () => {
    account.fetchInvitation.mockResolvedValue({
      email: "v@u.test",
      business_name: "Villa Urquiza",
      status: "valid",
      needs_password: true,
    });
    wrap("/invitacion?token=abc", <InvitationPage {...props} />);

    await choose("mi-clave-nueva", "otra-clave-xx");

    expect(await screen.findByText("Las dos claves no coinciden.")).toBeTruthy();
    expect(account.acceptInvitation).not.toHaveBeenCalled();
  });

  it.each([
    ["expired", true, "Este link venció"],
    ["used", true, "Ya tenés tu clave"],
    ["valid", false, "Ya tenés tu clave"],
  ] as const)("explains a %s link (needs_password %s)", async (status, needs, title) => {
    account.fetchInvitation.mockResolvedValue({
      email: "v@u.test",
      business_name: "Villa Urquiza",
      status,
      needs_password: needs,
    });
    wrap("/invitacion?token=abc", <InvitationPage {...props} />);

    expect(await screen.findByText(title)).toBeTruthy();
    expect(screen.queryByLabelText("Clave nueva")).toBeNull();
  });

  it("says an unknown link is not valid", async () => {
    account.fetchInvitation.mockRejectedValue(new ApiRequestError(404, "invitation_not_found"));
    wrap("/invitacion?token=zzz", <InvitationPage {...props} />);

    expect(await screen.findByText("Link no válido")).toBeTruthy();
  });
});

describe("ChangePasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("saves the new password and goes on to the panel", async () => {
    account.changePassword.mockResolvedValue(undefined);
    wrap("/clave", <ChangePasswordPage {...props} />);

    expect(screen.getByText(/ana@example.com/)).toBeTruthy();
    await choose("mi-clave-nueva", "mi-clave-nueva", "Guardar mi clave");

    expect(account.changePassword).toHaveBeenCalledWith("mi-clave-nueva");
    expect(await screen.findByText("Panel")).toBeTruthy();
  });

  it("shows the API's rule when the password is not accepted", async () => {
    account.changePassword.mockRejectedValue(new ApiRequestError(422, "password_is_email"));
    wrap("/clave", <ChangePasswordPage {...props} />);

    await choose("ana@example.com", "ana@example.com", "Guardar mi clave");

    expect(await screen.findByText("La clave no puede ser tu email.")).toBeTruthy();
  });
});

describe("RequireAccount", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends a temporary password to /cambiar-clave first", async () => {
    account.fetchAccount.mockResolvedValue({ email: "a@b.test", must_change_password: true });
    wrap("/guarded", <RequireAccount account={account}><p>Contenido</p></RequireAccount>);

    expect(await screen.findByText("Cambiar clave")).toBeTruthy();
  });

  it("lets everyone else through", async () => {
    account.fetchAccount.mockResolvedValue({ email: "a@b.test", must_change_password: false });
    wrap("/guarded", <RequireAccount account={account}><p>Contenido</p></RequireAccount>);

    expect(await screen.findByText("Contenido")).toBeTruthy();
  });
});

describe("ClaimInvitation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("tells someone nobody invited that the account is not enabled", async () => {
    const signUp = vi.fn().mockRejectedValue(new ApiRequestError(403, "not_invited"));
    wrap("/claim", <ClaimInvitation productName="inmo24x7" signUp={signUp} useAuth={useAuth} />);

    expect(await screen.findByText("Tu cuenta no está habilitada")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(signOut).toHaveBeenCalled();
  });

  it("joins the invited business without asking anything", async () => {
    const signUp = vi.fn().mockResolvedValue({});
    wrap("/claim", <ClaimInvitation productName="inmo24x7" signUp={signUp} useAuth={useAuth} />);

    await vi.waitFor(() => expect(signUp).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Tu cuenta no está habilitada")).toBeNull();
  });
});
