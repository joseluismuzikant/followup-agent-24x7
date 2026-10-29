import { ChatSimulator, KnownFactsPanel } from "@followup/ui";
import type { ChatMessage } from "@followup/ui";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const messages: ChatMessage[] = [
  { id: "1", author: "visitor", text: "Quiero alquilar en Palermo" },
  {
    id: "2",
    author: "agent",
    text: "¡Mirá estas opciones!",
    cards: [
      {
        id: "a",
        title: "2 ambientes amoblado",
        address: "Güemes 4300, Palermo",
        price_label: "$850.000 por mes",
        link: "/ejemplo/a",
        over_budget: true,
      },
    ],
  },
];

function renderChat(props: Partial<React.ComponentProps<typeof ChatSimulator>> = {}) {
  const onSend = vi.fn();
  const onReset = vi.fn();
  render(
    <ChatSimulator
      agentName="Sofía"
      businessName="Inmobiliaria Sur"
      messages={messages}
      onSend={onSend}
      onReset={onReset}
      {...props}
    />,
  );
  return { onSend, onReset, user: userEvent.setup() };
}

describe("ChatSimulator", () => {
  it("renders the header, bubbles and property cards", () => {
    renderChat({ resolveLink: (link) => `https://panel.example.com${link}` });

    expect(screen.getByText("Sofía · Inmobiliaria Sur")).toBeTruthy();
    expect(screen.getByText("Responde al instante")).toBeTruthy();
    expect(screen.getByText("Quiero alquilar en Palermo")).toBeTruthy();
    expect(screen.getByText("2 ambientes amoblado")).toBeTruthy();
    expect(screen.getByText("$850.000 por mes")).toBeTruthy();
    expect(screen.getByText("Un poco más de tu presupuesto")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ver fotos" }).getAttribute("href")).toBe(
      "https://panel.example.com/ejemplo/a",
    );
  });

  it("sends with Enter and adds a line with Shift+Enter", async () => {
    const { user, onSend } = renderChat();
    const input = screen.getByLabelText("Mensaje") as HTMLTextAreaElement;

    await user.type(input, "Hola{Shift>}{Enter}{/Shift}2 ambientes");
    expect(onSend).not.toHaveBeenCalled();
    expect(input.value).toBe("Hola\n2 ambientes");

    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("Hola\n2 ambientes");
    expect(input.value).toBe("");
  });

  it("blocks empty messages and sending while the agent is typing", async () => {
    const { user, onSend } = renderChat({ typing: true });

    expect(screen.getByRole("status").textContent).toContain("Sofía está escribiendo");
    await user.type(screen.getByLabelText("Mensaje"), "hola{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("links to the trace only when a message has one", () => {
    renderChat({
      messages: [
        { id: "1", author: "agent", text: "Hola", traceUrl: "https://smith.example/r/1" },
        { id: "2", author: "agent", text: "¿Zona?" },
      ],
    });

    const links = screen.getAllByRole("link", { name: "Ver traza" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://smith.example/r/1");
  });

  it("restarts with Reiniciar", async () => {
    const { user, onReset } = renderChat();

    await user.click(screen.getByRole("button", { name: "Reiniciar" }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });
});

describe("KnownFactsPanel", () => {
  it("shows Pendiente for what the agent does not know yet", () => {
    render(
      <KnownFactsPanel
        facts={[
          { key: "operation", label: "Operación", value: "Alquiler" },
          { key: "contact", label: "Contacto", value: null },
        ]}
      />,
    );

    expect(screen.getByText("Lo que el agente ya sabe")).toBeTruthy();
    expect(screen.getByText("Alquiler")).toBeTruthy();
    expect(screen.getByText("Pendiente")).toBeTruthy();
  });
});
