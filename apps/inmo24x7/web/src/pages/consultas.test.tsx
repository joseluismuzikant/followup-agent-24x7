import type { Lead, LeadDetail, LeadList } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelVisit,
  confirmVisit,
  downloadLeadsCsv,
  fetchLead,
  fetchLeads,
  releaseLead,
  sendTeamMessage,
  takeOverLead,
} from "../api/leads";
import { fetchMe } from "../api/me";
import { me } from "../test-fixtures";
import { ConsultasPage } from "./consultas";

vi.mock("../api/leads", () => ({
  fetchLeads: vi.fn(),
  fetchLead: vi.fn(),
  takeOverLead: vi.fn(),
  releaseLead: vi.fn(),
  sendTeamMessage: vi.fn(),
  confirmVisit: vi.fn(),
  cancelVisit: vi.fn(),
  downloadLeadsCsv: vi.fn(),
}));
vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));

const ME = me().profile.id;

function lead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: "l1",
    visitor_name: "Ana Pérez",
    contact: "+54 9 11 5555-0188",
    looking_for: "Alquiler · 2 amb. · Palermo · hasta $900.000",
    status: "visit_proposed",
    is_test: false,
    channel: "whatsapp",
    handed_off_at: "2026-11-02T15:00:00Z",
    hand_off_reason: "visit",
    created_at: "2026-11-02T14:50:00Z",
    last_activity_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    needs_attention: true,
    next_visit_at: "2026-11-07T13:30:00Z",
    ...overrides,
  };
}

function detail(overrides: Partial<LeadDetail> = {}): LeadDetail {
  return {
    ...lead(),
    answers: [
      { key: "operation", label: "Si busca comprar o alquilar", value: "Alquiler" },
      { key: "custom_1", label: "Garantía", value: "Propietaria" },
      { key: "visitor_name", label: "Nombre", value: "Ana Pérez" },
      { key: "contact", label: "Contacto", value: "+54 9 11 5555-0188" },
    ],
    status_history: [{ status: "visit_proposed", changed_at: "2026-11-02T14:58:00Z" }],
    visits: [
      {
        id: "v1",
        property_id: null,
        property_label: "2 ambientes luminoso · Gorriti 4800",
        starts_at: "2026-11-07T13:30:00Z",
        status: "proposed",
      },
    ],
    transcript: [
      {
        id: "m1",
        direction: "inbound",
        author: "visitor",
        text: "",
        cards: null,
        content_type: "audio",
        created_at: "2026-11-02T14:50:00Z",
      },
      {
        id: "m2",
        direction: "outbound",
        author: "agent",
        text: "¿Me lo escribís?",
        cards: null,
        content_type: "text",
        delivery_status: "read",
        created_at: "2026-11-02T14:50:05Z",
      },
      {
        id: "m3",
        direction: "outbound",
        author: "system",
        text: "El agente derivó la consulta a tu equipo",
        cards: null,
        content_type: "text",
        created_at: "2026-11-02T15:00:00Z",
      },
    ],
    control: { mode: "agent", by: null, changed_at: null },
    service_window: { open: true, expires_at: "2026-11-03T21:40:00Z" },
    ...overrides,
  };
}

function list(items: Lead[], counts = { attention: 1, visits: 1, all: 3 }): LeadList {
  return { items, total: items.length, page: 1, page_size: 25, counts };
}

let location = "";
function LocationProbe() {
  const current = useLocation();
  location = `${current.pathname}${current.search}`;
  return null;
}

function renderPage(path = "/consultas") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ConsultasPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("ConsultasPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me("agent"));
    vi.mocked(fetchLeads).mockResolvedValue(
      list([
        lead(),
        lead({ id: "l2", visitor_name: null, contact: "+54 9 11 4444-0000", status: "human_requested", is_test: true }),
      ]),
    );
    vi.mocked(fetchLead).mockResolvedValue(detail());
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("opens on Para atender with its count, ages, summaries and badges", async () => {
    renderPage();

    expect(await screen.findByRole("tab", { name: "Para atender · 1" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Para atender · 1" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    const items = within(screen.getByRole("list", { name: "Lista de consultas" }));
    const ana = within(items.getByRole("button", { name: /Ana Pérez/ }));
    expect(ana.getByText("12 min")).toBeTruthy();
    expect(ana.getByText("Alquiler · 2 amb. · Palermo · hasta $900.000")).toBeTruthy();
    expect(ana.getByText("Visita propuesta")).toBeTruthy();
    expect(items.getByText("+54 9 11 4444-0000")).toBeTruthy();
    expect(items.getByText("Pidió hablar con alguien")).toBeTruthy();
    expect(items.getByText("Prueba")).toBeTruthy();
    expect(vi.mocked(fetchLeads)).toHaveBeenCalledWith({
      tab: "attention",
      q: "",
      includeTest: true,
      page: 1,
    });
  });

  it("switches tabs and searches, keeping both in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ana Pérez");

    await user.click(screen.getByRole("tab", { name: "Visitas" }));
    await user.type(screen.getByRole("searchbox", { name: "Buscar por nombre, zona o teléfono" }), "palermo");

    await waitFor(() =>
      expect(vi.mocked(fetchLeads)).toHaveBeenLastCalledWith({
        tab: "visits",
        q: "palermo",
        includeTest: true,
        page: 1,
      }),
    );
    expect(location).toBe("/consultas?tab=visits&q=palermo");
  });

  it("shows an empty state per tab", async () => {
    vi.mocked(fetchLeads).mockResolvedValue(list([], { attention: 0, visits: 0, all: 0 }));
    renderPage("/consultas?tab=visits");

    expect(await screen.findByText("Todavía no hay visitas propuestas ni confirmadas.")).toBeTruthy();
  });

  it("exports the CSV with the current tab, search and toggle", async () => {
    const user = userEvent.setup();
    renderPage("/consultas?tab=all&q=ana");
    await screen.findByText("Ana Pérez");

    await user.click(screen.getByLabelText("Mostrar pruebas del simulador"));
    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));

    expect(vi.mocked(downloadLeadsCsv)).toHaveBeenCalledWith({
      tab: "all",
      q: "ana",
      includeTest: false,
    });
  });

  it("opens a lead from the list and from ?lead=", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Ana Pérez/ }));

    expect(location).toBe("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });
    expect(within(panel).getByText(/· por WhatsApp/)).toBeTruthy();
    expect(within(panel).getByText("Garantía")).toBeTruthy();
    expect(within(panel).getByText("Propietaria")).toBeTruthy();
    expect(within(panel).getByText("Audio")).toBeTruthy();
    expect(within(panel).getByText("Leído")).toBeTruthy();
    expect(within(panel).getByText("El agente derivó la consulta a tu equipo")).toBeTruthy();
    expect(within(panel).getByText("Espera tu confirmación")).toBeTruthy();
  });

  it("asks to take the conversation before replying", async () => {
    const user = userEvent.setup();
    vi.mocked(takeOverLead).mockResolvedValue(
      detail({ control: { mode: "human", by: { id: ME, name: "Luis" }, changed_at: null } }),
    );
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    expect(within(panel).getByText("Tomá la conversación para responder")).toBeTruthy();
    expect((within(panel).getByLabelText("Respuesta") as HTMLTextAreaElement).disabled).toBe(true);

    await user.click(within(panel).getByRole("button", { name: "Tomar la conversación" }));

    expect(vi.mocked(takeOverLead)).toHaveBeenCalledWith("l1");
    expect(await within(panel).findByRole("button", { name: "Devolver al agente" })).toBeTruthy();
    expect((within(panel).getByLabelText("Respuesta") as HTMLTextAreaElement).disabled).toBe(false);
    expect(within(panel).getByText(/Podés responder hasta las \d\d:\d\d/)).toBeTruthy();
  });

  it("confirms before taking a conversation someone else has", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchLead).mockResolvedValue(
      detail({ control: { mode: "human", by: { id: "other", name: "Marta" }, changed_at: null } }),
    );
    vi.mocked(takeOverLead).mockResolvedValue(detail());
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    expect(within(panel).getByText("Marta está atendiendo esta conversación.")).toBeTruthy();
    await user.click(within(panel).getByRole("button", { name: "Tomar la conversación" }));
    const dialog = await screen.findByRole("dialog", { name: "Tomar la conversación" });
    expect(within(dialog).getByText(/Marta está atendiendo esta consulta/)).toBeTruthy();
    expect(vi.mocked(takeOverLead)).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Tomarla" }));

    expect(vi.mocked(takeOverLead)).toHaveBeenCalledWith("l1");
  });

  it("sends a reply and gives the conversation back", async () => {
    const user = userEvent.setup();
    const mine = detail({ control: { mode: "human", by: { id: ME, name: "Luis" }, changed_at: null } });
    vi.mocked(fetchLead).mockResolvedValue(mine);
    vi.mocked(sendTeamMessage).mockResolvedValue(mine.transcript[1]);
    vi.mocked(releaseLead).mockResolvedValue(detail());
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    await user.type(within(panel).getByLabelText("Respuesta"), "Hola Ana, soy Luis");
    await user.click(within(panel).getByRole("button", { name: "Enviar" }));
    expect(vi.mocked(sendTeamMessage)).toHaveBeenCalledWith("l1", "Hola Ana, soy Luis");
    await waitFor(() =>
      expect((within(panel).getByLabelText("Respuesta") as HTMLTextAreaElement).value).toBe(""),
    );

    await user.click(within(panel).getByRole("button", { name: "Devolver al agente" }));
    expect(vi.mocked(releaseLead)).toHaveBeenCalledWith("l1");
  });

  it("disables the composer outside the 24-hour window", async () => {
    vi.mocked(fetchLead).mockResolvedValue(
      detail({
        control: { mode: "human", by: { id: ME, name: "Luis" }, changed_at: null },
        service_window: { open: false, expires_at: "2026-11-01T10:00:00Z" },
      }),
    );
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    expect(within(panel).getByText(/Pasaron más de 24 horas desde el último mensaje/)).toBeTruthy();
    expect((within(panel).getByLabelText("Respuesta") as HTMLTextAreaElement).disabled).toBe(true);
    expect(within(panel).getByRole("button", { name: "Confirmar visita" })).toBeTruthy();
  });

  it("confirms the visit at another time", async () => {
    const user = userEvent.setup();
    vi.mocked(confirmVisit).mockResolvedValue(
      detail({ status: "visit_confirmed", visits: [{ ...detail().visits[0], status: "confirmed" }] }),
    );
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    await user.click(within(panel).getByRole("button", { name: "Confirmar visita" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirmar visita" });
    const input = within(dialog).getByLabelText("Día y horario") as HTMLInputElement;
    // Proposed for Saturday 7/11 10:30 in Buenos Aires.
    expect(input.value).toBe("2026-11-07T10:30");
    await user.clear(input);
    await user.type(input, "2026-11-07T11:00");
    await user.click(within(dialog).getByRole("button", { name: "Confirmar visita" }));

    expect(vi.mocked(confirmVisit)).toHaveBeenCalledWith("l1", "v1", "2026-11-07T14:00:00.000Z");
    expect(await within(panel).findByText("Le avisamos a la persona")).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: "Confirmar visita" })).toBeNull();
  });

  it("confirms at the proposed time without sending one", async () => {
    const user = userEvent.setup();
    vi.mocked(confirmVisit).mockResolvedValue(detail({ status: "visit_confirmed" }));
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    await user.click(within(panel).getByRole("button", { name: "Confirmar visita" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirmar visita" });
    await user.click(within(dialog).getByRole("button", { name: "Confirmar visita" }));

    expect(vi.mocked(confirmVisit)).toHaveBeenCalledWith("l1", "v1", undefined);
  });

  it("cancels the visit with an optional message", async () => {
    const user = userEvent.setup();
    vi.mocked(cancelVisit).mockResolvedValue(
      detail({ status: "human_requested", visits: [{ ...detail().visits[0], status: "cancelled" }] }),
    );
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    await user.click(within(panel).getByRole("button", { name: "Cancelar visita" }));
    const dialog = await screen.findByRole("dialog", { name: "Cancelar visita" });
    await user.type(within(dialog).getByLabelText("Mensaje para la persona (opcional)"), "Se cayó");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar visita" }));

    expect(vi.mocked(cancelVisit)).toHaveBeenCalledWith("l1", "v1", "Se cayó");
    expect(await within(panel).findByText("El equipo la canceló")).toBeTruthy();
  });

  it("shows API errors in Spanish", async () => {
    const user = userEvent.setup();
    const { ApiRequestError } = await import("@followup/api-client-inmo24x7");
    vi.mocked(confirmVisit).mockRejectedValue(new ApiRequestError(409, "template_not_configured"));
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    await user.click(within(panel).getByRole("button", { name: "Confirmar visita" }));
    await user.click(
      within(await screen.findByRole("dialog", { name: "Confirmar visita" })).getByRole("button", {
        name: "Confirmar visita",
      }),
    );

    expect(await within(panel).findByText(/hace falta la plantilla de confirmación/)).toBeTruthy();
  });

  it("polls the open lead and keeps the draft reply", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const mine = detail({ control: { mode: "human", by: { id: ME, name: "Luis" }, changed_at: null } });
    vi.mocked(fetchLead).mockResolvedValue(mine);
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });
    await user.type(within(panel).getByLabelText("Respuesta"), "Hola An");

    vi.mocked(fetchLead).mockResolvedValue({
      ...mine,
      transcript: [
        ...mine.transcript,
        {
          id: "m4",
          direction: "inbound",
          author: "visitor",
          text: "¿Siguen ahí?",
          cards: null,
          content_type: "text",
          created_at: "2026-11-02T15:10:00Z",
        },
      ],
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });

    expect(await within(panel).findByText("¿Siguen ahí?")).toBeTruthy();
    expect((within(panel).getByLabelText("Respuesta") as HTMLTextAreaElement).value).toBe("Hola An");
  });

  it("is read-only for viewers", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("viewer"));
    renderPage("/consultas?lead=l1");
    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });

    expect(within(panel).getByText("El agente derivó la consulta a tu equipo")).toBeTruthy();
    expect(within(panel).queryByRole("button")).toBeNull();
    expect(within(panel).queryByLabelText("Respuesta")).toBeNull();
  });
});
