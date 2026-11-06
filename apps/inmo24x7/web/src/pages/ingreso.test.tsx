import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { account } from "../api/client";
import { readDevToken, signOutDev } from "../lib/dev-session";
import { IngresoPage } from "./ingreso";

const mode = vi.hoisted(() => ({ current: "supabase" as "supabase" | "dev" }));
const auth = vi.hoisted(() => ({ signInWithPassword: vi.fn(), resetPasswordForEmail: vi.fn() }));

vi.mock("../lib/auth-mode", () => ({
  get authMode() {
    return mode.current;
  },
}));
vi.mock("../lib/supabase", () => ({ getSupabase: vi.fn(() => ({ auth })) }));
vi.mock("../api/client", () => ({ account: { devSignIn: vi.fn() } }));

async function signIn(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Clave"), password);
  await user.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("IngresoPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mode.current = "supabase";
    signOutDev();
    auth.signInWithPassword.mockResolvedValue({ error: null });
  });

  it("asks for email and password, with no Google, magic link or sign-up", () => {
    render(<IngresoPage />);

    expect(screen.getByText("inmo24x7")).toBeTruthy();
    expect(screen.getByLabelText("Clave")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Google/ })).toBeNull();
    expect(screen.queryByText(/Modo desarrollo/)).toBeNull();
  });

  it("signs in with Supabase", async () => {
    render(<IngresoPage />);

    await signIn("dueno@inmobiliariasur.test", "local-1234");

    expect(auth.signInWithPassword).toHaveBeenCalledWith({
      email: "dueno@inmobiliariasur.test",
      password: "local-1234",
    });
  });

  it("shows an error for an empty form", async () => {
    const user = userEvent.setup();
    render(<IngresoPage />);

    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(screen.getByText("Ingresá tu email y tu clave.")).toBeTruthy();
    expect(auth.signInWithPassword).not.toHaveBeenCalled();
  });

  it("in dev mode checks the password with the API and keeps the dev token", async () => {
    mode.current = "dev";
    vi.mocked(account.devSignIn).mockResolvedValue("dev:dueno@inmobiliariasur.test");
    render(<IngresoPage />);

    expect(screen.getByText(/local-1234/)).toBeTruthy();
    await signIn("dueno@inmobiliariasur.test", "local-1234");

    expect(readDevToken()).toBe("dev:dueno@inmobiliariasur.test");
    expect(auth.signInWithPassword).not.toHaveBeenCalled();
  });
});
