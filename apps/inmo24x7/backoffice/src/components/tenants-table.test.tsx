import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { businessRow } from "../test-fixtures";
import { TenantsTable } from "./tenants-table";

function renderTable(rows = [businessRow()]) {
  render(
    <MemoryRouter>
      <TenantsTable businesses={rows} />
    </MemoryRouter>,
  );
}

describe("TenantsTable (S8)", () => {
  it("shows business, owner, plan, onboarding, WhatsApp badge, inquiries and date", () => {
    renderTable();

    const row = screen.getByRole("link", { name: "Inmobiliaria Sur" }).closest("tr") as HTMLElement;
    expect(screen.getByRole("link", { name: "Inmobiliaria Sur" }).getAttribute("href")).toBe(
      "/negocios/6d57c8d4-6b5b-4fac-8e50-23b6f0c0f210",
    );
    for (const text of ["duena@sur.test", "Prueba · 12 días", "3 de 5", "Conectado", "7"]) {
      expect(within(row).getByText(text)).toBeTruthy();
    }
  });

  it("labels every WhatsApp state, Pro, pending owners and suspended businesses", () => {
    renderTable([
      businessRow({ id: "a", name: "A", whatsapp: "verification_pending" }),
      businessRow({ id: "b", name: "B", whatsapp: "action_required", status: "suspended" }),
      businessRow({
        id: "c",
        name: "C",
        whatsapp: "not_connected",
        owner_pending: true,
        plan: { plan: "pro", name: "Pro", trial_days_left: null },
      }),
    ]);

    expect(screen.getByText("Verificación pendiente")).toBeTruthy();
    expect(screen.getByText("Acción requerida")).toBeTruthy();
    expect(screen.getByText("Sin conectar")).toBeTruthy();
    expect(screen.getByText("Suspendido")).toBeTruthy();
    expect(screen.getByText("Pro")).toBeTruthy();
    expect(screen.getByText(/todavía no entró/)).toBeTruthy();
  });
});
