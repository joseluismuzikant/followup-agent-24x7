import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { SimulatorReply } from "@followup/api-client-inmo24x7";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchSimulator, resetSimulator, sendSimulatorMessage } from "../api/simulator";
import { simulatorState } from "../test-fixtures";
import { SimulatorView } from "./SimulatorView";

vi.mock("../api/simulator", () => ({
  fetchSimulator: vi.fn(),
  sendSimulatorMessage: vi.fn(),
  resetSimulator: vi.fn(),
}));

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SimulatorView />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

const reply: SimulatorReply = {
  messages: [
    {
      id: "out-1",
      direction: "outbound",
      author: "agent",
      text: "Contame: ¿zona o barrio?",
      cards: null,
      created_at: "2026-10-29T12:00:00Z",
    },
  ],
  known: [
    { key: "operation", label: "Si busca comprar o alquilar", value: "Alquiler" },
    { key: "zone", label: "Zona o barrio", value: null },
    { key: "visitor_name", label: "Nombre", value: null },
    { key: "contact", label: "Contacto", value: null },
  ],
};

async function send(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(await screen.findByLabelText("Mensaje"), `${text}{Enter}`);
}

describe("SimulatorView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSimulator).mockResolvedValue(simulatorState());
  });

  it("shows the visitor bubble while the agent answers, then the reply and the panel", async () => {
    let answer: (value: SimulatorReply) => void = () => {};
    vi.mocked(sendSimulatorMessage).mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    const user = renderView();

    await send(user, "Quiero alquilar");

    expect(screen.getByText("Quiero alquilar")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("está escribiendo");
    vi.mocked(fetchSimulator).mockResolvedValue(
      simulatorState({ messages: reply.messages, known: reply.known }),
    );
    answer(reply);

    expect(await screen.findByText("Contame: ¿zona o barrio?")).toBeTruthy();
    expect(screen.getByText("Alquiler")).toBeTruthy();
    expect(screen.getAllByText("Pendiente")).toHaveLength(3);
  });

  it("offers to resend when the agent is unavailable", async () => {
    vi.mocked(sendSimulatorMessage)
      .mockRejectedValueOnce(new ApiRequestError(503, "agent_unavailable"))
      .mockResolvedValueOnce(reply);
    const user = renderView();

    await send(user, "Quiero alquilar");

    expect(await screen.findByText("Tu agente no pudo responder ahora. Probá de nuevo.")).toBeTruthy();
    expect(screen.getByText("Quiero alquilar")).toBeTruthy();
    vi.mocked(fetchSimulator).mockResolvedValue(
      simulatorState({ messages: reply.messages, known: reply.known }),
    );
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Contame: ¿zona o barrio?")).toBeTruthy();
    expect(vi.mocked(sendSimulatorMessage).mock.calls.map((call) => call[0])).toEqual([
      "Quiero alquilar",
      "Quiero alquilar",
    ]);
    expect(screen.queryByText("Tu agente no pudo responder ahora. Probá de nuevo.")).toBeNull();
  });

  it("shows the daily limit without a resend button", async () => {
    vi.mocked(sendSimulatorMessage).mockRejectedValue(
      new ApiRequestError(429, "simulator_limit_reached"),
    );
    const user = renderView();

    await send(user, "Hola");

    expect(await screen.findByText(/Llegaste al límite de mensajes de prueba de hoy/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("asks to restart when the agent changed and Reiniciar loads the new thread", async () => {
    vi.mocked(fetchSimulator).mockResolvedValue(simulatorState({ config_outdated: true }));
    vi.mocked(resetSimulator).mockResolvedValue(simulatorState({ agent_name: "Lucía" }));
    const user = renderView();

    expect(
      await screen.findByText("Cambiaste tu agente. Reiniciá la conversación para probar los cambios."),
    ).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reiniciar" }));

    expect(await screen.findByText("Lucía · Inmobiliaria Sur")).toBeTruthy();
    expect(
      screen.queryByText("Cambiaste tu agente. Reiniciá la conversación para probar los cambios."),
    ).toBeNull();
  });

  it("shows the sample properties banner only while the tenant has none of its own", async () => {
    renderView();

    expect(await screen.findByText("Está usando propiedades de ejemplo")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Subir mis propiedades" }).getAttribute("href")).toBe(
      "/propiedades",
    );
  });

  it("hides the banner when the tenant has its own properties", async () => {
    vi.mocked(fetchSimulator).mockResolvedValue(simulatorState({ uses_sample_properties: false }));
    renderView();

    await screen.findByText("Sofía · Inmobiliaria Sur");
    expect(screen.queryByText("Está usando propiedades de ejemplo")).toBeNull();
  });
});
