import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelInvoice,
  downloadImportErrors,
  fetchInvoice,
  fetchInvoices,
  importInvoices,
  markInvoicePaid,
  promiseInvoice,
  removePromise,
} from "../api/invoices";
import { fetchMe } from "../api/me";
import { errorsReport, invoice, invoiceDetail, invoiceList, me } from "../test-fixtures";
import { FacturasPage } from "./facturas";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/invoices", () => ({
  fetchInvoices: vi.fn(),
  fetchInvoice: vi.fn(),
  updateInvoice: vi.fn(),
  markInvoicePaid: vi.fn(),
  cancelInvoice: vi.fn(),
  promiseInvoice: vi.fn(),
  removePromise: vi.fn(),
  importInvoices: vi.fn(),
  downloadImportErrors: vi.fn(),
  downloadImportTemplate: vi.fn(),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FacturasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("FacturasPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchInvoices).mockResolvedValue(
      invoiceList(
        [
          invoice(),
          invoice({
            id: "inv-2",
            client_name: "Edificio Alvear",
            client_subtitle: null,
            number: "A 0001-00000088",
            amount: "95000.00",
            due_date: "2026-11-06",
            status: { kind: "due_soon", label: "Por vencer", days_overdue: null },
          }),
        ],
        { total: 32 },
      ),
    );
    vi.mocked(fetchInvoice).mockResolvedValue(invoiceDetail());
  });

  it("lists the invoices with tab counts, columns, pagination and the ARCA notice", async () => {
    renderPage();

    const row = (await screen.findByText("Consorcio Rivadavia 4500")).closest("tr")!;
    expect(within(row).getByText("B 0003-00001245")).toBeTruthy();
    expect(within(row).getByText("Vencida · 23 días")).toBeTruthy();
    expect(within(row).getByText("—")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Pendientes (32)" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Vencidas (13)" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Prometidas (0)" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Pagadas este mes (8)" })).toBeTruthy();
    expect(screen.getByText("Mostrando 1 a 25 de 32")).toBeTruthy();
    expect(screen.getByText(/no emite facturas ante ARCA/)).toBeTruthy();
  });

  it("switches tabs and searches", async () => {
    const user = renderPage();
    await screen.findByText("Consorcio Rivadavia 4500");

    await user.click(screen.getByRole("tab", { name: /Vencidas/ }));
    expect(fetchInvoices).toHaveBeenLastCalledWith({ tab: "overdue", q: "", page: 1 });

    await user.type(screen.getByRole("searchbox", { name: "Buscar facturas" }), "0003-00001245");
    expect(fetchInvoices).toHaveBeenLastCalledWith({ tab: "overdue", q: "0003-00001245", page: 1 });
  });

  it("opens the drawer and marks an invoice as paid", async () => {
    vi.mocked(markInvoicePaid).mockResolvedValue(
      invoiceDetail({
        lifecycle: "paid",
        status: { kind: "paid", label: "Pagada · Transferencia", days_overdue: null },
        payment: { paid_at: "2026-11-03", paid_via: "transfer", paid_via_label: "Transferencia", reference: "OP-991" },
      }),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Consorcio Rivadavia 4500" }));
    const drawer = await screen.findByRole("dialog", { name: "Factura B 0003-00001245" });
    expect(within(drawer).getByText("Abono mantenimiento septiembre")).toBeTruthy();
    expect(within(drawer).getByText("+54 9 11 5555-1234")).toBeTruthy();

    await user.click(within(drawer).getByRole("button", { name: "Marcar como pagada" }));
    await user.clear(within(drawer).getByLabelText("Fecha de pago"));
    await user.type(within(drawer).getByLabelText("Fecha de pago"), "2026-11-03");
    await user.type(within(drawer).getByLabelText("Referencia (opcional)"), "OP-991");
    await user.click(within(drawer).getByRole("button", { name: "Marcar como pagada" }));

    expect(markInvoicePaid).toHaveBeenCalledWith("inv-1", {
      paid_at: "2026-11-03",
      paid_via: "transfer",
      reference: "OP-991",
    });
    expect(await within(drawer).findByText("Pagada · Transferencia")).toBeTruthy();
    expect(within(drawer).getByText("OP-991")).toBeTruthy();
    expect(within(drawer).queryByRole("button", { name: "Anular" })).toBeNull();
  });

  it("shows what comes next and registers a promise that pauses the reminders", async () => {
    vi.mocked(fetchInvoices).mockResolvedValue(
      invoiceList([invoice({ next_action: "Recordatorio mañana 9:00", next_action_kind: "reminder" })]),
    );
    vi.mocked(fetchInvoice).mockResolvedValue(
      invoiceDetail({ next_action: "Recordatorio mañana 9:00", next_action_kind: "reminder" }),
    );
    const promised = invoiceDetail({
      lifecycle: "promised",
      promised_until: "2026-11-20",
      status: { kind: "promised", label: "Con promesa · hasta 20/11", days_overdue: null },
      next_action: "Pausado: promesa hasta 20/11",
      next_action_kind: "promised",
    });
    vi.mocked(promiseInvoice).mockResolvedValue(promised);
    vi.mocked(removePromise).mockResolvedValue(invoiceDetail());
    const user = renderPage();

    const row = (await screen.findByText("Consorcio Rivadavia 4500")).closest("tr")!;
    expect(within(row).getByText("Recordatorio mañana 9:00")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Consorcio Rivadavia 4500" }));
    const drawer = await screen.findByRole("dialog", { name: "Factura B 0003-00001245" });
    await user.click(within(drawer).getByRole("button", { name: "Registrar promesa de pago" }));
    const date = within(drawer).getByLabelText("Prometió pagar hasta el");
    await user.clear(date);
    await user.type(date, "2026-11-20");
    await user.click(within(drawer).getByRole("button", { name: "Registrar promesa" }));

    expect(promiseInvoice).toHaveBeenCalledWith("inv-1", "2026-11-20");
    expect(await within(drawer).findByText("Pausado: promesa hasta 20/11")).toBeTruthy();
    expect(within(drawer).getByText("Con promesa · hasta 20/11")).toBeTruthy();
    await user.click(within(drawer).getByRole("button", { name: "Quitar promesa" }));
    expect(removePromise).toHaveBeenCalledWith("inv-1");
  });

  it("asks for a reason before cancelling", async () => {
    vi.mocked(cancelInvoice).mockResolvedValue(
      invoiceDetail({
        lifecycle: "cancelled",
        status: { kind: "cancelled", label: "Anulada", days_overdue: null },
        cancelled_reason: "Nota de crédito",
      }),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Consorcio Rivadavia 4500" }));
    const drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("button", { name: "Anular" }));
    await user.click(within(drawer).getByRole("button", { name: "Anular" }));
    expect(within(drawer).getByRole("alert").textContent).toBe("Contanos por qué la anulás.");
    expect(cancelInvoice).not.toHaveBeenCalled();

    await user.type(within(drawer).getByLabelText("Motivo"), "Nota de crédito");
    await user.click(within(drawer).getByRole("button", { name: "Anular" }));
    expect(cancelInvoice).toHaveBeenCalledWith("inv-1", "Nota de crédito");
    expect(await within(drawer).findByText("Anulada: Nota de crédito")).toBeTruthy();
  });

  it("hides the actions from staff", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("staff"));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Consorcio Rivadavia 4500" }));
    const drawer = await screen.findByRole("dialog");
    await within(drawer).findByText("Abono mantenimiento septiembre");
    expect(within(drawer).queryByRole("button", { name: "Marcar como pagada" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Importar facturas" })).toBeNull();
  });

  it("imports a file and shows the report with the errors download", async () => {
    vi.mocked(importInvoices).mockResolvedValue(errorsReport);
    vi.mocked(downloadImportErrors).mockResolvedValue();
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Importar facturas" }));
    const file = new File(["x"], "facturas-con-errores.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/Arrastrá tu archivo/), file);

    const report = await screen.findByRole("region", { name: "Resultado de la importación" });
    expect(within(report).getByText("Importamos 35 de 40")).toBeTruthy();
    expect(within(report).getByText("Fila 7: el CUIT no es válido.")).toBeTruthy();
    expect(within(report).getByText("Fila 31: el monto no es un número.")).toBeTruthy();
    expect(
      within(report).getByText("Fila 9: la factura ya figuraba pagada; no la cambiamos."),
    ).toBeTruthy();

    await user.click(within(report).getByRole("button", { name: "Descargar las 4 con errores" }));
    expect(downloadImportErrors).toHaveBeenCalledWith("imp-1");
  });

  it("says when nothing matches the search", async () => {
    vi.mocked(fetchInvoices).mockResolvedValue(invoiceList([], { total: 0 }));
    const user = renderPage();
    await user.type(screen.getByRole("searchbox"), "zzz");
    expect(await screen.findByText("No hay facturas que coincidan con la búsqueda.")).toBeTruthy();
  });
});
