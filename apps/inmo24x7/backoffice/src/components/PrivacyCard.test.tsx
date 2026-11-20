import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { PrivacyContact } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  closeBusiness,
  deleteContactData,
  fetchClosureSummary,
  findContacts,
  setContactDoNotContact,
} from "../api/backoffice";
import { businessDetail } from "../test-fixtures";
import { PrivacyCard } from "./PrivacyCard";

vi.mock("../api/backoffice", () => ({
  findContacts: vi.fn(),
  deleteContactData: vi.fn(),
  setContactDoNotContact: vi.fn(),
  fetchClosureSummary: vi.fn(),
  closeBusiness: vi.fn(),
}));

function contact(overrides: Partial<PrivacyContact> = {}): PrivacyContact {
  return {
    wa_id: "5491155550188",
    phone: "+54 9 11 5555-0188",
    names: ["Ana Pérez"],
    leads: 1,
    messages: 12,
    visits: 1,
    last_activity_at: "2026-11-18T14:00:00Z",
    do_not_contact: false,
    ...overrides,
  };
}

function renderCard(overrides = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const business = businessDetail({ name: "Inmobiliaria Sur", ...overrides });
  render(
    <QueryClientProvider client={queryClient}>
      <PrivacyCard business={business} queryKey={["business", business.id]} />
    </QueryClientProvider>,
  );
  return { user: userEvent.setup(), business };
}

describe("Datos y privacidad", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(findContacts).mockResolvedValue([contact()]);
  });

  it("finds a contact, shows what goes and deletes it once the phone is typed", async () => {
    vi.mocked(deleteContactData).mockResolvedValue({
      leads: 1,
      conversations: 1,
      messages: 12,
      visits: 1,
    });
    const { user, business } = renderCard();

    await user.type(screen.getByLabelText("Teléfono o nombre"), "ana");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    const found = within(await screen.findByRole("list", { name: "Contactos encontrados" }));
    expect(found.getByText("+54 9 11 5555-0188")).toBeTruthy();
    expect(found.getByText(/1 consulta · 12 mensajes · 1 visita/)).toBeTruthy();
    expect(findContacts).toHaveBeenCalledWith(business.id, "ana");

    await user.click(found.getByRole("button", { name: "Eliminar datos" }));
    const dialog = within(screen.getByRole("dialog", { name: "Eliminar datos de +54 9 11 5555-0188" }));
    expect(dialog.getByText(/Se conserva el «no contactar»/)).toBeTruthy();
    expect(dialog.getByText("Lo que ya se envió a Tokko o al webhook queda en esos sistemas.")).toBeTruthy();
    const submit = dialog.getByRole("button", { name: "Eliminar datos" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await user.type(dialog.getByLabelText("Escribí el teléfono para confirmar"), "11 5555-0188");
    await user.click(submit);

    expect(deleteContactData).toHaveBeenCalledWith(business.id, "5491155550188", "11 5555-0188");
    expect(
      await screen.findByText("Listo: eliminamos 1 consulta y 12 mensajes de +54 9 11 5555-0188."),
    ).toBeTruthy();
  });

  it("explains a phone that does not match", async () => {
    vi.mocked(deleteContactData).mockRejectedValue(
      new ApiRequestError(422, "confirmation_mismatch"),
    );
    const { user } = renderCard();
    await user.type(screen.getByLabelText("Teléfono o nombre"), "0188");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    await user.click(await screen.findByRole("button", { name: "Eliminar datos" }));
    const dialog = within(screen.getByRole("dialog"));

    await user.type(dialog.getByLabelText("Escribí el teléfono para confirmar"), "11 4444");
    await user.click(dialog.getByRole("button", { name: "Eliminar datos" }));

    expect((await dialog.findByRole("alert")).textContent).toBe(
      "Lo que escribiste no coincide. Revisalo y probá de nuevo.",
    );
  });

  it("marks a contact or any number as do-not-contact", async () => {
    vi.mocked(setContactDoNotContact).mockResolvedValue({
      wa_id: "5491144440000",
      phone: "+54 9 11 4444-0000",
      do_not_contact: true,
    });
    const { user, business } = renderCard();
    await user.type(screen.getByLabelText("Teléfono o nombre"), "ana");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    const found = within(await screen.findByRole("list", { name: "Contactos encontrados" }));

    await user.click(found.getByRole("button", { name: "Marcar como no contactar" }));
    expect(setContactDoNotContact).toHaveBeenCalledWith(business.id, "+54 9 11 5555-0188", true);

    const section = within(screen.getByRole("region", { name: "No contactar un número" }));
    await user.type(section.getByLabelText("Teléfono"), "11 4444-0000");
    await user.click(section.getByRole("button", { name: "Marcar como no contactar" }));

    expect(setContactDoNotContact).toHaveBeenLastCalledWith(business.id, "11 4444-0000", true);
    expect(
      await section.findByText("+54 9 11 4444-0000 no va a recibir mensajes de este negocio."),
    ).toBeTruthy();
  });

  it("closes the account after showing what goes and typing its name", async () => {
    vi.mocked(fetchClosureSummary).mockResolvedValue({
      name: "Inmobiliaria Sur",
      properties: 20,
      leads: 35,
      conversations: 40,
      messages: 512,
      users: 2,
      users_kept: 1,
      whatsapp_connected: true,
      closing: false,
    });
    vi.mocked(closeBusiness).mockResolvedValue({
      ...(await fetchClosureSummary("t1")),
      closing: true,
    });
    const { user, business } = renderCard();

    await user.click(screen.getByRole("button", { name: "Cerrar cuenta y eliminar datos" }));
    const dialog = within(screen.getByRole("dialog", { name: "Cerrar Inmobiliaria Sur" }));
    const goes = within(await dialog.findByRole("list", { name: "Lo que se borra" }));
    expect(goes.getByText("20 propiedades y sus importaciones")).toBeTruthy();
    expect(goes.getByText(/2 usuarios \(1 sigue entrando a su otro negocio\)/)).toBeTruthy();
    expect(goes.getByText(/nuestra app deja de recibir sus mensajes en Meta/)).toBeTruthy();
    expect(goes.getByText(/las integraciones y sus claves/)).toBeTruthy();
    expect(dialog.getByText("Lo que ya se envió a Tokko o al webhook queda en esos sistemas.")).toBeTruthy();
    await user.type(
      dialog.getByLabelText("Escribí el nombre del negocio para confirmar"),
      "Inmobiliaria Sur",
    );
    await user.click(dialog.getByRole("button", { name: "Cerrar cuenta y eliminar datos" }));

    expect(closeBusiness).toHaveBeenCalledWith(business.id, "Inmobiliaria Sur");
  });
});
