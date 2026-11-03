import type { Lead, LeadDetail } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchLead, fetchLeads } from "../api/leads";
import { ConsultasPage } from "./consultas";

vi.mock("../api/leads", () => ({ fetchLeads: vi.fn(), fetchLead: vi.fn() }));

function lead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: "l1",
    visitor_name: "Ana Pérez",
    contact: "+54 9 11 5555-1234",
    looking_for: "Alquiler · 2 amb. · Palermo · hasta $900.000",
    status: "visit_proposed",
    is_test: true,
    channel: "simulator",
    handed_off_at: "2026-11-02T15:00:00Z",
    hand_off_reason: "visit",
    created_at: "2026-11-02T14:50:00Z",
    last_activity_at: "2026-11-02T15:00:00Z",
    ...overrides,
  };
}

const detail: LeadDetail = {
  ...lead(),
  answers: [
    { key: "operation", label: "Si busca comprar o alquilar", value: "Alquiler" },
    { key: "zone", label: "Zona o barrio", value: "Palermo" },
    { key: "visitor_name", label: "Nombre", value: "Ana Pérez" },
    { key: "contact", label: "Contacto", value: "+54 9 11 5555-1234" },
  ],
  status_history: [
    { status: "qualifying", changed_at: "2026-11-02T14:50:00Z" },
    { status: "visit_proposed", changed_at: "2026-11-02T14:58:00Z" },
  ],
  visits: [
    {
      id: "v1",
      property_id: "p1",
      property_label: "Monoambiente amoblado · Charcas 4100",
      starts_at: "2026-11-03T16:00:00Z",
      status: "proposed",
    },
  ],
  transcript: [
    {
      id: "m1",
      direction: "inbound",
      author: "visitor",
      text: "Hola",
      cards: null,
      content_type: "text",
      created_at: "2026-11-02T14:50:00Z",
    },
    {
      id: "m2",
      direction: "outbound",
      author: "system",
      text: "El agente derivó la consulta a tu equipo",
      cards: null,
      content_type: "text",
      created_at: "2026-11-02T15:00:00Z",
    },
  ],
};

function renderPage(path = "/consultas") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ConsultasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("ConsultasPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchLeads).mockResolvedValue({
      items: [
        lead(),
        lead({ id: "l2", visitor_name: null, contact: "+54 9 11 4444-0000", status: "human_requested", is_test: false }),
        lead({ id: "l3", visitor_name: "Juan", status: "qualifying", is_test: false }),
      ],
      total: 3,
      page: 1,
      page_size: 20,
    });
    vi.mocked(fetchLead).mockResolvedValue(detail);
  });

  it("shows the S5 status badges, the contact when there is no name, and the Prueba badge", async () => {
    renderPage();

    const ana = (await screen.findByText("Ana Pérez")).closest("tr") as HTMLElement;
    expect(within(ana).getByText("Visita propuesta")).toBeTruthy();
    expect(within(ana).getByText("Prueba")).toBeTruthy();
    expect(within(ana).getByText("Alquiler · 2 amb. · Palermo · hasta $900.000")).toBeTruthy();
    const phone = screen.getByText("+54 9 11 4444-0000").closest("tr") as HTMLElement;
    expect(within(phone).getByText("Pidió hablar con alguien")).toBeTruthy();
    expect(within(phone).queryByText("Prueba")).toBeNull();
    expect(screen.getByText("Calificando")).toBeTruthy();
  });

  it("hides simulator tests with the toggle", async () => {
    const user = renderPage();
    await screen.findByText("Ana Pérez");

    await user.click(screen.getByLabelText("Mostrar pruebas del simulador"));

    expect(vi.mocked(fetchLeads)).toHaveBeenLastCalledWith({ includeTest: false, page: 1 });
  });

  it("opens the detail with answers, the proposed visit and the transcript, read-only", async () => {
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: /Ana Pérez/ }));

    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });
    expect(within(panel).getByText("Monoambiente amoblado · Charcas 4100")).toBeTruthy();
    expect(within(panel).getByText("Esperando la confirmación del equipo")).toBeTruthy();
    expect(within(panel).getByText("El agente derivó la consulta a tu equipo")).toBeTruthy();
    expect(within(panel).getByText("Palermo")).toBeTruthy();
    // Takeover and confirming the visit come on Day 6.
    expect(within(panel).queryByRole("button")).toBeNull();
  });

  it("shows WhatsApp leads as real, with delivery labels and media types", async () => {
    vi.mocked(fetchLead).mockResolvedValue({
      ...detail,
      is_test: false,
      channel: "whatsapp",
      transcript: [
        {
          id: "w1",
          direction: "inbound",
          author: "visitor",
          text: "",
          cards: null,
          content_type: "audio",
          created_at: "2026-11-02T14:50:00Z",
        },
        {
          id: "w2",
          direction: "outbound",
          author: "agent",
          text: "Por ahora solo puedo leer mensajes de texto. ¿Me lo escribís?",
          cards: null,
          content_type: "text",
          delivery_status: "read",
          created_at: "2026-11-02T14:50:05Z",
        },
        {
          id: "w3",
          direction: "outbound",
          author: "agent",
          text: "¿Seguís ahí?",
          cards: null,
          content_type: "text",
          delivery_status: "failed",
          created_at: "2026-11-03T16:00:00Z",
        },
      ],
    });

    renderPage("/consultas?lead=l2");

    const panel = await screen.findByRole("complementary", { name: "Detalle de la consulta" });
    expect(within(panel).getByText(/por WhatsApp/)).toBeTruthy();
    expect(within(panel).queryByText("Prueba")).toBeNull();
    expect(within(panel).getByText("Audio")).toBeTruthy();
    expect(within(panel).getByText("Leído")).toBeTruthy();
    expect(within(panel).getByText("No se pudo enviar")).toBeTruthy();
    expect(vi.mocked(fetchLead)).toHaveBeenCalledWith("l2");
    const row = screen.getByText("+54 9 11 4444-0000").closest("tr") as HTMLElement;
    expect(within(row).getByText("en el simulador")).toBeTruthy();
  });
});
