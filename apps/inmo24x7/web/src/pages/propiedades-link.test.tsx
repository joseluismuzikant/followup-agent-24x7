import type {
  ConditionSettings,
  ListingDraft,
  Property,
  PropertyList,
} from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import {
  createProperty,
  fetchConditionSettings,
  fetchProperties,
  readListingLink,
  readListingText,
  refreshFromLink,
  updateProperty,
} from "../api/properties";
import { EMPTY_CONDITIONS } from "../lib/conditions";
import { me, phoneViewport } from "../test-fixtures";
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
  fetchConditionSettings: vi.fn(),
  saveConditionSettings: vi.fn(),
  readListingLink: vi.fn(),
  readListingText: vi.fn(),
  refreshFromLink: vi.fn(),
}));

const ZONAPROP = "https://www.zonaprop.com.ar/propiedades/clasificado/2-amb-gorriti-555.html";

function settings(): ConditionSettings {
  return {
    rent: { ...EMPTY_CONDITIONS },
    sale: { ...EMPTY_CONDITIONS },
    warn_before_visit: true,
    offer_alternatives: true,
    notify_mismatches: true,
  };
}

function property(overrides: Partial<Property> = {}): Property {
  return {
    id: "p1",
    title: "2 ambientes luminoso",
    address: "Gorriti 4800",
    operation: "rent",
    zone: "Palermo",
    price: 800000,
    currency: "ARS",
    rooms: 2,
    link: ZONAPROP,
    status: "published",
    inquiries: 0,
    created_at: "2026-11-02T12:00:00Z",
    updated_at: "2026-11-02T12:00:00Z",
    conditions: { ...EMPTY_CONDITIONS },
    effective_conditions: { ...EMPTY_CONDITIONS },
    from_defaults: [],
    source: "manual",
    external_id: null,
    external_ref: null,
    ...overrides,
  };
}

function listing(overrides: Partial<ListingDraft> = {}): ListingDraft {
  return {
    link: ZONAPROP,
    title: "2 ambientes luminoso con balcón",
    address: "Gorriti 4800",
    operation: "rent",
    zone: "Palermo",
    price: 850000,
    currency: "ARS",
    rooms: 2,
    status: null,
    conditions: { ...EMPTY_CONDITIONS, mascotas: true },
    image_url: "https://img.portal.example/portada.jpg",
    floor_area_m2: 48,
    sources: {
      title: "structured",
      address: "model",
      operation: "structured",
      zone: "structured",
      price: "model",
      currency: "structured",
      rooms: "structured",
      mascotas: "model",
    },
    problem: null,
    message: null,
    portal: "Zonaprop",
    warnings: [],
    duplicate: null,
    ...overrides,
  };
}

const BLOCKED =
  "Zonaprop no deja leer la página. Abrí tu publicación, seleccioná todo (Ctrl+A), copiá (Ctrl+C) y pegalo acá.";

function page(items: Property[]): PropertyList {
  return { items, total: items.length, page: 1, page_size: 20 };
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

function fieldOf(dialog: HTMLElement, label: string): HTMLElement {
  return within(dialog).getByLabelText(label).closest('[data-slot="form-field"]') as HTMLElement;
}

async function openLinkDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Cargar desde un link" }));
  return screen.getByRole("dialog", { name: "Cargar desde un link" });
}

describe("Cargar desde un link", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchConditionSettings).mockResolvedValue(settings());
    vi.mocked(fetchProperties).mockResolvedValue(page([]));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the link and opens the form pre-filled, marking what the model read", async () => {
    vi.mocked(readListingLink).mockResolvedValue(listing());
    vi.mocked(createProperty).mockResolvedValue(property());
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    expect(within(dialog).getByText("Usá links de tus propias publicaciones.")).toBeTruthy();
    await user.type(within(dialog).getByLabelText("Link de la publicación"), ZONAPROP);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    expect(readListingLink).toHaveBeenCalledWith(ZONAPROP);
    const form = await screen.findByRole("dialog", { name: "Revisá la propiedad" });
    // The preview: cover image, title and price.
    const preview = within(form).getByRole("region", { name: "Publicación leída" });
    expect(within(preview).getByText("2 ambientes luminoso con balcón")).toBeTruthy();
    expect(within(preview).getByText("$ 850.000")).toBeTruthy();
    expect(preview.querySelector("img")?.getAttribute("src")).toBe(
      "https://img.portal.example/portada.jpg",
    );
    // Pre-filled fields; only those the model read say "Revisá este dato".
    expect((within(form).getByLabelText("Título") as HTMLInputElement).value).toBe(
      "2 ambientes luminoso con balcón",
    );
    expect((within(form).getByLabelText("Link del aviso") as HTMLInputElement).value).toBe(
      ZONAPROP,
    );
    expect(fieldOf(form, "Precio").textContent).toContain("Revisá este dato");
    expect(fieldOf(form, "Dirección").textContent).toContain("Revisá este dato");
    expect(fieldOf(form, "Título").textContent).not.toContain("Revisá este dato");
    expect(within(form).getByText(/Revisá las condiciones/)).toBeTruthy();

    // The agent edits and saves as usual: nothing was saved before this.
    expect(createProperty).not.toHaveBeenCalled();
    await user.clear(within(form).getByLabelText("Precio"));
    await user.type(within(form).getByLabelText("Precio"), "830.000");
    await user.click(within(form).getByRole("button", { name: "Guardar" }));

    expect(vi.mocked(createProperty).mock.calls[0][0]).toMatchObject({
      title: "2 ambientes luminoso con balcón",
      address: "Gorriti 4800",
      operation: "rent",
      zone: "Palermo",
      price: 830000,
      currency: "ARS",
      rooms: 2,
      link: ZONAPROP,
      conditions: expect.objectContaining({ mascotas: true }),
    });
  });

  it("offers to open a property already loaded with that link", async () => {
    vi.mocked(readListingLink).mockResolvedValue(
      listing({ title: "", duplicate: property({ title: "Mi 2 ambientes" }) }),
    );
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    await user.type(within(dialog).getByLabelText("Link de la publicación"), ZONAPROP);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    expect((await within(dialog).findByRole("status")).textContent).toContain(
      "Ya cargaste esta propiedad: Mi 2 ambientes.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Abrirla" }));

    expect(await screen.findByRole("dialog", { name: "Editar propiedad" })).toBeTruthy();
  });

  it("switches to the text tab when the portal blocks reading, keeping the link", async () => {
    vi.mocked(readListingLink).mockResolvedValue(
      listing({
        title: "",
        address: "",
        operation: null,
        zone: "",
        price: null,
        currency: null,
        rooms: null,
        image_url: null,
        floor_area_m2: null,
        sources: {},
        conditions: { ...EMPTY_CONDITIONS },
        problem: "blocked",
        message: BLOCKED,
      }),
    );
    vi.mocked(readListingText).mockResolvedValue(
      listing({
        sources: { title: "model", price: "model", rooms: "model", zone: "model" },
        image_url: null,
      }),
    );
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    await user.type(within(dialog).getByLabelText("Link de la publicación"), ZONAPROP);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    expect((await within(dialog).findByRole("status")).textContent).toBe(BLOCKED);
    expect(
      within(dialog)
        .getByRole("radio", { name: "Pegar texto de la publicación" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect((within(dialog).getByLabelText("Link de la publicación") as HTMLInputElement).value).toBe(
      ZONAPROP,
    );
    await user.click(within(dialog).getByLabelText("Texto de la publicación"));
    await user.paste("Alquiler $ 780.000 · 2 ambientes · Palermo · Gorriti 4800");
    await user.click(within(dialog).getByRole("button", { name: "Leer texto" }));

    expect(readListingText).toHaveBeenCalledWith(
      "Alquiler $ 780.000 · 2 ambientes · Palermo · Gorriti 4800",
      ZONAPROP,
    );
    const form = await screen.findByRole("dialog", { name: "Revisá la propiedad" });
    // Everything came from the model: every field read is marked.
    for (const label of ["Título", "Precio", "Ambientes", "Zona o barrio"]) {
      expect(fieldOf(form, label).textContent).toContain("Revisá este dato");
    }
  });

  it("opens the form with the link when the page could not be read", async () => {
    vi.mocked(readListingLink).mockResolvedValue(
      listing({
        title: "",
        address: "",
        operation: null,
        zone: "",
        price: null,
        currency: null,
        rooms: null,
        image_url: null,
        sources: {},
        problem: "unreachable",
        message:
          "El portal no nos dejó leer la página. Completá los datos a mano; el link queda guardado.",
      }),
    );
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    await user.type(within(dialog).getByLabelText("Link de la publicación"), ZONAPROP);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    const form = await screen.findByRole("dialog", { name: "Revisá la propiedad" });
    expect(within(form).getByRole("status").textContent).toBe(
      "El portal no nos dejó leer la página. Completá los datos a mano; el link queda guardado.",
    );
    expect((within(form).getByLabelText("Link del aviso") as HTMLInputElement).value).toBe(
      ZONAPROP,
    );
    expect((within(form).getByLabelText("Título") as HTMLInputElement).value).toBe("");
  });

  it("asks for the link before reading", async () => {
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    expect(within(dialog).getByRole("alert").textContent).toBe("Pegá el link de la publicación.");
    expect(readListingLink).not.toHaveBeenCalled();
  });

  it("works on a 390 px phone", async () => {
    phoneViewport(390);
    vi.mocked(readListingLink).mockResolvedValue(listing());
    const user = renderPage();

    const dialog = await openLinkDialog(user);
    await user.type(within(dialog).getByLabelText("Link de la publicación"), ZONAPROP);
    await user.click(within(dialog).getByRole("button", { name: "Leer publicación" }));

    expect(await screen.findByRole("dialog", { name: "Revisá la propiedad" })).toBeTruthy();
  });
});

describe("Actualizar desde el link", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchConditionSettings).mockResolvedValue(settings());
    vi.mocked(fetchProperties).mockResolvedValue(page([property()]));
  });

  it("shows what changed and applies it field by field before saving", async () => {
    vi.mocked(refreshFromLink).mockResolvedValue({
      draft: listing(),
      changes: [
        { field: "title", current: "2 ambientes luminoso", read: "2 ambientes luminoso con balcón" },
        { field: "price", current: 800000, read: 850000 },
      ],
    });
    vi.mocked(updateProperty).mockResolvedValue(property({ price: 850000 }));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Editar: 2 ambientes luminoso" }));
    const form = screen.getByRole("dialog", { name: "Editar propiedad" });
    await user.click(within(form).getByRole("button", { name: "Actualizar desde el link" }));

    const changes = await within(form).findByRole("list", { name: "Cambios en la publicación" });
    expect(changes.textContent).toContain("Precio: 800.000 → 850.000");
    await user.click(within(form).getByRole("button", { name: "Aplicar Precio" }));

    expect((within(form).getByLabelText("Precio") as HTMLInputElement).value).toBe("850000");
    expect((within(form).getByLabelText("Título") as HTMLInputElement).value).toBe(
      "2 ambientes luminoso",
    ); // not applied
    expect(updateProperty).not.toHaveBeenCalled();
    await user.click(within(form).getByRole("button", { name: "Guardar" }));

    expect(vi.mocked(updateProperty).mock.calls[0]).toEqual([
      "p1",
      expect.objectContaining({ price: 850000, title: "2 ambientes luminoso" }),
    ]);
  });

  it("asks for the text when the portal blocks the link", async () => {
    vi.mocked(refreshFromLink)
      .mockResolvedValueOnce({
        draft: listing({ problem: "blocked", message: BLOCKED, sources: {} }),
        changes: [],
      })
      .mockResolvedValueOnce({
        draft: listing(),
        changes: [{ field: "status", current: "published", read: "paused" }],
      });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Editar: 2 ambientes luminoso" }));
    const form = screen.getByRole("dialog", { name: "Editar propiedad" });
    await user.click(within(form).getByRole("button", { name: "Actualizar desde el link" }));
    expect((await within(form).findByRole("status")).textContent).toBe(BLOCKED);
    await user.click(within(form).getByLabelText("Texto de la publicación"));
    await user.paste("Reservado. Alquiler $ 850.000, 2 ambientes en Palermo.");
    await user.click(within(form).getByRole("button", { name: "Leer texto" }));

    expect(refreshFromLink).toHaveBeenLastCalledWith(
      "p1",
      "Reservado. Alquiler $ 850.000, 2 ambientes en Palermo.",
    );
    expect(
      (await within(form).findByRole("list", { name: "Cambios en la publicación" })).textContent,
    ).toContain("Estado: Publicada → Pausada");
  });

  it("is not offered for Tokko listings", async () => {
    vi.mocked(fetchProperties).mockResolvedValue(
      page([property({ source: "tokko", external_id: "1" })]),
    );
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Editar: 2 ambientes luminoso" }));

    const form = screen.getByRole("dialog", { name: "Editar propiedad" });
    expect(within(form).queryByRole("button", { name: "Actualizar desde el link" })).toBeNull();
  });
});
