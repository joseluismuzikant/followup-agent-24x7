import { ApiRequestError } from "@followup/api-client-cuentas-claras";
import type { Client, ClientDetail } from "@followup/api-client-cuentas-claras";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createClient, fetchClient, fetchClients } from "../api/clients";
import { fetchMe } from "../api/me";
import { client, me } from "../test-fixtures";
import { ClientePage } from "./cliente";
import { ClientesPage } from "./clientes";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/clients", () => ({
  fetchClients: vi.fn(),
  fetchClient: vi.fn(),
  createClient: vi.fn(),
  updateClient: vi.fn(),
}));
vi.mock("../api/invoices", () => ({ fetchInvoice: vi.fn() }));

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/clientes" element={<ClientesPage />} />
          <Route path="/clientes/:id" element={<ClientePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

const withWhatsapp: Client = { ...client() };
delete (withWhatsapp as Partial<ClientDetail>).invoices;
const withoutWhatsapp = {
  ...withWhatsapp,
  id: "cli-2",
  name: "Edificio Alvear",
  subtitle: null,
  cuit: null,
  whatsapp: null,
  whatsapp_display: null,
  missing_whatsapp: true,
  open_invoices: 1,
  owed_ars: "95000.00",
  owed_usd: "1200.00",
};

describe("ClientesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchClients).mockResolvedValue({
      items: [withWhatsapp, withoutWhatsapp],
      total: 2,
      page: 1,
      page_size: 25,
      total_pages: 1,
    });
  });

  it("lists the clients with the Sin WhatsApp badge and what they owe", async () => {
    renderAt("/clientes");

    const row = (await screen.findByText("Edificio Alvear")).closest("tr")!;
    expect(within(row).getByText("Sin WhatsApp")).toBeTruthy();
    expect(within(row).getByText(/USD 1\.200/)).toBeTruthy();
    const other = screen.getByText("Consorcio Rivadavia 4500").closest("tr")!;
    expect(within(other).getByText("+54 9 11 5555-1234")).toBeTruthy();
    expect(within(other).getByText("30-71234567-1")).toBeTruthy();
  });

  it("filters by missing WhatsApp and searches", async () => {
    const user = renderAt("/clientes");
    await screen.findByText("Edificio Alvear");

    await user.click(screen.getByLabelText("Solo sin WhatsApp"));
    expect(fetchClients).toHaveBeenLastCalledWith({ q: "", missingWhatsapp: true, page: 1 });

    await user.type(screen.getByRole("searchbox", { name: "Buscar clientes" }), "alvear");
    expect(fetchClients).toHaveBeenLastCalledWith({ q: "alvear", missingWhatsapp: true, page: 1 });
  });

  it("validates the form before creating a client", async () => {
    vi.mocked(createClient).mockResolvedValue(client({ id: "cli-9", name: "Torre Norte" }));
    vi.mocked(fetchClient).mockResolvedValue(client({ id: "cli-9", name: "Torre Norte" }));
    const user = renderAt("/clientes");
    await screen.findByText("Edificio Alvear");

    await user.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    const dialog = screen.getByRole("dialog", { name: "Nuevo cliente" });
    await user.type(within(dialog).getByLabelText("CUIT (opcional)"), "30-71234567-2");
    await user.type(within(dialog).getByLabelText("WhatsApp"), "5555");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(within(dialog).getByText("Ingresá el nombre del cliente.")).toBeTruthy();
    expect(within(dialog).getByText(/El CUIT no es válido/)).toBeTruthy();
    expect(within(dialog).getByText(/código de área/)).toBeTruthy();
    expect(createClient).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("Nombre o razón social"), "Torre Norte");
    await user.clear(within(dialog).getByLabelText("CUIT (opcional)"));
    await user.type(within(dialog).getByLabelText("CUIT (opcional)"), "30-71234567-1");
    await user.clear(within(dialog).getByLabelText("WhatsApp"));
    await user.type(within(dialog).getByLabelText("WhatsApp"), "11 5555-1234");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(createClient).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Torre Norte", cuit: "30-71234567-1", whatsapp: "11 5555-1234" }),
    );
    expect(await screen.findByText("Torre Norte")).toBeTruthy();
  });

  it("shows the API's message when the CUIT is taken", async () => {
    vi.mocked(createClient).mockRejectedValue(
      new ApiRequestError(409, "cuit_taken"),
    );
    const user = renderAt("/clientes");
    await screen.findByText("Edificio Alvear");

    await user.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Nombre o razón social"), "Otro");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(await within(dialog).findByText("Ya tenés otro cliente con ese CUIT.")).toBeTruthy();
  });

  it("shows a client's detail with its invoices", async () => {
    vi.mocked(fetchClient).mockResolvedValue(
      client({
        invoices: [
          {
            id: "inv-1",
            number: "B 0003-00001245",
            due_date: "2026-10-10",
            amount: "180000.00",
            currency: "ARS",
            status: "overdue",
            status_label: "Vencida · 23 días",
          },
        ],
      }),
    );
    renderAt("/clientes/cli-1");

    expect(await screen.findByText("Consorcio Rivadavia 4500")).toBeTruthy();
    expect(screen.getByText("Marta Gómez")).toBeTruthy();
    const invoices = screen.getByRole("region", { name: "Facturas del cliente" });
    expect(within(invoices).getByText("B 0003-00001245")).toBeTruthy();
    expect(within(invoices).getByText("Vencida · 23 días")).toBeTruthy();
  });
});
