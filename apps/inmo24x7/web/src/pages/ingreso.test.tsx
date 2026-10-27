import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IngresoPage } from "./ingreso";
import { supabase } from "../lib/supabase";

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      signInWithOAuth: vi.fn(),
      signInWithOtp: vi.fn(),
    },
  },
}));

const signInWithOAuth = vi.mocked(supabase.auth.signInWithOAuth);
const signInWithOtp = vi.mocked(supabase.auth.signInWithOtp);

describe("IngresoPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signInWithOAuth.mockResolvedValue({ error: null } as never);
    signInWithOtp.mockResolvedValue({ error: null } as never);
  });

  it("shows the Google button and the magic link form", () => {
    render(<IngresoPage />);

    expect(screen.getByRole("button", { name: "Continuar con Google" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Enviarme un link para entrar" }),
    ).toBeTruthy();
  });

  it("sends a magic link and shows the sent state", async () => {
    const user = userEvent.setup();
    render(<IngresoPage />);

    await user.type(screen.getByLabelText("Email"), "duena@example.com");
    await user.click(screen.getByRole("button", { name: "Enviarme un link para entrar" }));

    expect(signInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({ email: "duena@example.com" }),
    );
    expect(await screen.findByText(/Te enviamos un link/)).toBeTruthy();
  });

  it("shows an error for an empty email", async () => {
    const user = userEvent.setup();
    render(<IngresoPage />);

    await user.click(screen.getByRole("button", { name: "Enviarme un link para entrar" }));

    expect(signInWithOtp).not.toHaveBeenCalled();
    expect(screen.getByText("Ingresá tu email.")).toBeTruthy();
  });
});
