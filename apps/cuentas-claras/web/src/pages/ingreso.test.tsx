import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { IngresoPage } from "./ingreso";

vi.mock("../lib/auth-mode", () => ({ authMode: "dev" }));
vi.mock("../api/client", () => ({ account: { devSignIn: vi.fn() } }));

describe("IngresoPage", () => {
  it("shows Cuentas Claras's copy and the seeded dev account", () => {
    render(
      <MemoryRouter>
        <IngresoPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Cuentas Claras")).toBeTruthy();
    expect(screen.getByText("Entrá a tu panel")).toBeTruthy();
    expect(screen.getByText("Cobrá sin reclamar.")).toBeTruthy();
    expect(screen.getByPlaceholderText("dueno@ascensoresdelta.test")).toBeTruthy();
    expect(screen.getByLabelText("Clave")).toBeTruthy();
  });
});
