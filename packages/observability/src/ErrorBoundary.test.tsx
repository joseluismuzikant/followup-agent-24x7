import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("render failed");
}

describe("AppErrorBoundary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the Spanish fallback with Recargar", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <AppErrorBoundary>
        <Broken />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("alert").textContent).toContain("Algo salió mal. Ya nos llegó el aviso.");
    expect(screen.getByRole("button", { name: "Recargar" })).toBeTruthy();
  });

  it("renders the app when nothing fails", () => {
    render(
      <AppErrorBoundary>
        <p>Inicio</p>
      </AppErrorBoundary>,
    );

    expect(screen.getByText("Inicio")).toBeTruthy();
  });
});
