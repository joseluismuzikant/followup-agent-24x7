import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { ImportReport, Property, PropertyList } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import {
  createProperty,
  downloadImportErrors,
  fetchProperties,
  importProperties,
  setPropertyPublished,
} from "../api/properties";
import { me } from "../test-fixtures";
import { PropiedadesPage } from "./propiedades";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/properties", () => ({
  fetchProperties: vi.fn(),
  createProperty: vi.fn(),
  updateProperty: vi.fn(),
  setPropertyPublished: vi.fn(),
  importProperties: vi.fn(),
  downloadImportErrors: vi.fn(),
  downloadImportTemplate: vi.fn(),
}));

function property(overrides: Partial<Property> = {}): Property {
  return {
    id: "p1",
    title: "2 ambientes luminoso",
    address: "Gorriti 4800",
    operation: "rent",
    zone: "Palermo",
    price: 850000,
    currency: "ARS",
    rooms: 2,
    link: "https://www.inmobiliariasur.example/propiedades/gorriti-4800",
    status: "published",
    inquiries: 3,
    created_at: "2026-11-02T12:00:00Z",
    updated_at: "2026-11-02T12:00:00Z",
    ...overrides,
  };
}

function page(items: Property[], total = items.length): PropertyList {
  return { items, total, page: 1, page_size: 20 };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <PropiedadesPage />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

const errorsReport: ImportReport = {
  id: "imp-1",
  file_name: "propiedades-con-errores.csv",
  total: 5,
  imported: 2,
  created: 2,
  updated: 0,
  failed: 3,
  errors: [
    "Fila 3: falta el precio.",
    "Fila 5: el link no es una dirección web válida.",
    "Fila 6: la operación tiene que ser «venta» o «alquiler».",
  ],
};

describe("PropiedadesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchProperties).mockResolvedValue(
      page([property(), property({ id: "p2", title: "Loft", operation: "sale", currency: "USD", price: 155000, status: "paused" })], 23),
    );
  });

  it("lists properties with price, status, inquiries and pagination", async () => {
    renderPage();

    const row = (await screen.findByText("2 ambientes luminoso")).closest("tr") as HTMLElement;
    expect(within(row).getByText("$ 850.000")).toBeTruthy();
    expect(within(row).getByText("Publicada")).toBeTruthy();
    expect(within(row).getByText("Alquiler")).toBeTruthy();
    expect(within(row).getByRole("link", { name: "ver aviso" }).getAttribute("href")).toContain(
      "gorriti-4800",
    );
    expect(within(row).getByText("3")).toBeTruthy();
    const loft = screen.getByText("Loft").closest("tr") as HTMLElement;
    expect(within(loft).getByText("USD 155.000")).toBeTruthy();
    expect(within(loft).getByText("Pausada")).toBeTruthy();
    expect(screen.getByText("Mostrando 1 a 20 de 23")).toBeTruthy();
  });

  it("publishes and pauses from the list", async () => {
    vi.mocked(setPropertyPublished).mockResolvedValue(property({ status: "paused" }));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Pausar: 2 ambientes luminoso" }));
    await user.click(screen.getByRole("button", { name: "Publicar: Loft" }));

    expect(vi.mocked(setPropertyPublished).mock.calls).toEqual([
      ["p1", false],
      ["p2", true],
    ]);
  });

  it("imports a file and shows the S7 report with the errors download", async () => {
    vi.mocked(importProperties).mockResolvedValue(errorsReport);
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Importar CSV o Excel" }));
    const file = new File(["titulo"], "propiedades-con-errores.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/Arrastrá tu archivo/), file);

    expect(await screen.findByText("Importamos 2 de 5")).toBeTruthy();
    for (const error of errorsReport.errors) {
      expect(screen.getByText(error)).toBeTruthy();
    }
    expect(vi.mocked(importProperties).mock.calls[0][0].name).toBe("propiedades-con-errores.csv");
    await user.click(screen.getByRole("button", { name: "Descargar las 3 con errores" }));
    expect(downloadImportErrors).toHaveBeenCalledWith("imp-1");
  });

  it("explains import failures in Spanish", async () => {
    vi.mocked(importProperties).mockRejectedValue(new ApiRequestError(413, "import_too_large"));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Importar CSV o Excel" }));
    await user.upload(screen.getByLabelText(/Arrastrá tu archivo/), new File(["x"], "x.csv"));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "El archivo es muy grande: hasta 5 MB y 2.000 propiedades por vez.",
    );
  });

  it("validates the form field by field before creating", async () => {
    vi.mocked(createProperty).mockResolvedValue(property());
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Agregar una" }));
    const dialog = screen.getByRole("dialog", { name: "Agregar una propiedad" });
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(within(dialog).getByText("Falta el título.")).toBeTruthy();
    expect(within(dialog).getByText("Ingresá un precio mayor a cero.")).toBeTruthy();
    expect(createProperty).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("Título"), "3 ambientes con cochera");
    await user.type(within(dialog).getByLabelText("Dirección"), "Guatemala 5200");
    await user.type(within(dialog).getByLabelText("Zona o barrio"), "Palermo");
    await user.type(within(dialog).getByLabelText("Precio"), "1.250.000");
    await user.type(within(dialog).getByLabelText("Ambientes"), "3");
    await user.type(within(dialog).getByLabelText("Link del aviso"), "www.sin-esquema.com");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(within(dialog).getByText("El link no es una dirección web válida.")).toBeTruthy();

    await user.clear(within(dialog).getByLabelText("Link del aviso"));
    await user.type(within(dialog).getByLabelText("Link del aviso"), "https://inmo.example/p/1");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(createProperty).toHaveBeenCalledWith({
      title: "3 ambientes con cochera",
      address: "Guatemala 5200",
      operation: "rent",
      zone: "Palermo",
      price: 1250000,
      currency: "ARS",
      rooms: 3,
      link: "https://inmo.example/p/1",
      status: "published",
    });
  });

  it("shows the link conflict from the API", async () => {
    vi.mocked(createProperty).mockRejectedValue(new ApiRequestError(409, "property_link_taken"));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Agregar una" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Título"), "Depto");
    await user.type(within(dialog).getByLabelText("Dirección"), "Calle 1");
    await user.type(within(dialog).getByLabelText("Zona o barrio"), "Palermo");
    await user.type(within(dialog).getByLabelText("Precio"), "100000");
    await user.type(within(dialog).getByLabelText("Ambientes"), "1");
    await user.type(within(dialog).getByLabelText("Link del aviso"), "https://inmo.example/p/1");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(await within(dialog).findByText("Ya tenés otra propiedad con ese link.")).toBeTruthy();
  });

  it("is read-only for viewers", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("viewer"));
    renderPage();

    await screen.findByText("2 ambientes luminoso");
    expect(screen.queryByRole("button", { name: "Agregar una" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Importar CSV o Excel" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Pausar/ })).toBeNull();
  });

  it("searches by address or zone and filters by operation", async () => {
    const user = renderPage();
    await screen.findByText("2 ambientes luminoso");

    await user.type(screen.getByLabelText("Buscar por dirección o zona"), "nuñez");
    await user.click(screen.getByRole("radio", { name: "Venta" }));

    expect(vi.mocked(fetchProperties)).toHaveBeenLastCalledWith({
      search: "nuñez",
      operation: "sale",
      page: 1,
    });
  });
});
