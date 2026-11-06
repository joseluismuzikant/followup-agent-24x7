import type { SupabaseClient } from "@supabase/supabase-js";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AccountApi } from "./account";
import { ApiRequestError } from "./api";
import { readDevToken, signOutDev } from "./auth/dev-session";
import { SignIn } from "./SignIn";

const auth = { signInWithPassword: vi.fn(), resetPasswordForEmail: vi.fn() };
const getSupabase = () => ({ auth }) as unknown as SupabaseClient;
const account = {
  fetchAccount: vi.fn(),
  changePassword: vi.fn(),
  fetchInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  devSignIn: vi.fn(),
} satisfies AccountApi;

function renderSignIn(authMode: "dev" | "supabase") {
  return render(
    <SignIn
      productName="Cuentas Claras"
      title="Entrá a tu panel"
      description="Cobrá sin reclamar."
      authMode={authMode}
      getSupabase={getSupabase}
      account={account}
    />,
  );
}

async function fill(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Clave"), password);
  await user.click(screen.getByRole("button", { name: "Entrar" }));
  return user;
}

describe("SignIn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signOutDev();
    auth.signInWithPassword.mockResolvedValue({ error: null });
    auth.resetPasswordForEmail.mockResolvedValue({ error: null });
  });

  it("shows each product's own copy, and no way to sign up", () => {
    renderSignIn("supabase");

    expect(screen.getByText("Cuentas Claras")).toBeTruthy();
    expect(screen.getByText("Cobrá sin reclamar.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Google/ })).toBeNull();
    expect(screen.getByText(/Las cuentas las crea un administrador/)).toBeTruthy();
  });

  it("signs in with email and password through Supabase", async () => {
    renderSignIn("supabase");

    await fill("Ana@Example.com", "mi-clave-1");

    expect(auth.signInWithPassword).toHaveBeenCalledWith({
      email: "ana@example.com",
      password: "mi-clave-1",
    });
  });

  it("says when the email or the password is wrong", async () => {
    auth.signInWithPassword.mockResolvedValue({ error: { status: 400 } });
    renderSignIn("supabase");

    await fill("ana@example.com", "otra");

    expect(await screen.findByText("El email o la clave no son correctos.")).toBeTruthy();
  });

  it("sends the reset email to the typed address", async () => {
    renderSignIn("supabase");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Email"), "ana@example.com");
    await user.click(screen.getByRole("button", { name: "¿Olvidaste tu clave?" }));

    expect(auth.resetPasswordForEmail).toHaveBeenCalledWith("ana@example.com", {
      redirectTo: `${window.location.origin}/cambiar-clave`,
    });
    expect(await screen.findByText(/te enviamos un link para elegir una clave nueva/)).toBeTruthy();
  });

  it("checks the password with the API in dev mode", async () => {
    account.devSignIn.mockResolvedValue("dev:nuevo@local.test");
    renderSignIn("dev");

    await fill("nuevo@local.test", "temporal-1234");

    expect(account.devSignIn).toHaveBeenCalledWith("nuevo@local.test", "temporal-1234");
    expect(readDevToken()).toBe("dev:nuevo@local.test");
    expect(auth.signInWithPassword).not.toHaveBeenCalled();
  });

  it("keeps a wrong dev password out", async () => {
    account.devSignIn.mockRejectedValue(new ApiRequestError(401, "invalid_credentials"));
    renderSignIn("dev");

    await fill("nuevo@local.test", "mala");

    expect(await screen.findByText("El email o la clave no son correctos.")).toBeTruthy();
    expect(readDevToken()).toBeNull();
  });
});
