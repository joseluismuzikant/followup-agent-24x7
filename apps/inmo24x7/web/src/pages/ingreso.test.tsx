import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { readDevToken, signOutDev } from "../lib/dev-session";
import { getSupabase } from "../lib/supabase";
import { IngresoPage } from "./ingreso";

const mode = vi.hoisted(() => ({ current: "supabase" as "supabase" | "dev" }));
const auth = vi.hoisted(() => ({ signInWithOAuth: vi.fn(), signInWithOtp: vi.fn() }));

vi.mock("../lib/auth-mode", () => ({
  get authMode() {
    return mode.current;
  },
}));
vi.mock("../lib/supabase", () => ({ getSupabase: vi.fn(() => ({ auth })) }));

describe("IngresoPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mode.current = "supabase";
    signOutDev();
    auth.signInWithOAuth.mockResolvedValue({ error: null });
    auth.signInWithOtp.mockResolvedValue({ error: null });
  });

  it("shows the Google button and the magic link form", () => {
    render(<IngresoPage />);

    expect(screen.getByRole("button", { name: "Continuar con Google" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Enviarme un link para entrar" }),
    ).toBeTruthy();
    expect(screen.queryByText("Modo desarrollo")).toBeNull();
  });

  it("sends a magic link and shows the sent state", async () => {
    const user = userEvent.setup();
    render(<IngresoPage />);

    await user.type(screen.getByLabelText("Email"), "duena@example.com");
    await user.click(screen.getByRole("button", { name: "Enviarme un link para entrar" }));

    expect(auth.signInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({ email: "duena@example.com" }),
    );
    expect(await screen.findByText(/Te enviamos un link/)).toBeTruthy();
  });

  it("shows an error for an empty email", async () => {
    const user = userEvent.setup();
    render(<IngresoPage />);

    await user.click(screen.getByRole("button", { name: "Enviarme un link para entrar" }));

    expect(auth.signInWithOtp).not.toHaveBeenCalled();
    expect(screen.getByText("Ingresá tu email.")).toBeTruthy();
  });

  it("in dev mode shows only the development box and signs in with a dev token", async () => {
    mode.current = "dev";
    const user = userEvent.setup();
    render(<IngresoPage />);

    expect(screen.getByText("Modo desarrollo")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Continuar con Google" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enviarme un link para entrar" })).toBeNull();

    await user.type(screen.getByLabelText("Email de prueba"), "Dueno@InmobiliariaSur.test");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(readDevToken()).toBe("dev:dueno@inmobiliariasur.test");
    expect(getSupabase).not.toHaveBeenCalled();
  });
});
