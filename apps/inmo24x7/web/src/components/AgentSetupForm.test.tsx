import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { agentSetup, defaultConfig } from "../test-fixtures";
import { AgentSetupForm } from "./AgentSetupForm";

function renderForm(props: Partial<React.ComponentProps<typeof AgentSetupForm>> = {}) {
  const onSubmit = vi.fn();
  render(
    <AgentSetupForm
      setup={agentSetup()}
      businessName="Inmobiliaria Sur"
      submitLabel="Guardar y probar mi agente"
      onSubmit={onSubmit}
      {...props}
    />,
  );
  return { onSubmit, user: userEvent.setup() };
}

const questionLabels = () =>
  screen
    .getAllByLabelText(/^Pregunta \d+$/)
    .map((input) => (input as HTMLInputElement).value);

describe("AgentSetupForm", () => {
  it("shows a live greeting preview", async () => {
    const { user } = renderForm();
    expect(screen.getByText("«Hola, soy Sofía, de Inmobiliaria Sur»")).toBeTruthy();

    const name = screen.getByLabelText("Nombre del agente");
    await user.clear(name);
    await user.type(name, "Lucía");

    expect(screen.getByText("«Hola, soy Lucía, de Inmobiliaria Sur»")).toBeTruthy();
  });

  it("resets to the recommended setup without saving", async () => {
    const { user, onSubmit } = renderForm();
    const name = screen.getByLabelText("Nombre del agente");
    await user.clear(name);
    await user.type(name, "Lucía");
    await user.click(screen.getByRole("radio", { name: "Formal" }));
    await user.click(screen.getByRole("radio", { name: "Lunes a sábado, 9 a 13" }));
    await user.click(screen.getByRole("button", { name: "+ Agregar una pregunta" }));

    await user.click(screen.getByRole("button", { name: "Usar lo recomendado" }));

    expect((screen.getByLabelText("Nombre del agente") as HTMLInputElement).value).toBe("Sofía");
    expect(screen.getByRole("radio", { name: "Cercano" }).getAttribute("aria-checked")).toBe("true");
    expect(
      screen.getByRole("radio", { name: "Lunes a viernes, 9 a 18" }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(questionLabels()).toEqual(defaultConfig.qualification_questions.map((q) => q.label));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("adds a custom question and deletes it", async () => {
    const { user } = renderForm();

    await user.click(screen.getByRole("button", { name: "+ Agregar una pregunta" }));
    expect(questionLabels().at(-1)).toBe("Nueva pregunta");

    await user.click(screen.getByRole("button", { name: "Eliminar: Nueva pregunta" }));
    expect(questionLabels()).toHaveLength(3);
    // Built-in questions cannot be deleted.
    expect(screen.queryByRole("button", { name: /^Eliminar: Zona/ })).toBeNull();
  });

  it("sends new questions without a key so the server assigns one", async () => {
    const saved = {
      ...defaultConfig,
      qualification_questions: [
        ...defaultConfig.qualification_questions,
        { key: "custom_3", label: "Mascotas", kind: "text" as const, options: [], enabled: true },
      ],
    };
    const { user, onSubmit } = renderForm({ setup: agentSetup({ config: saved, version: 4 }) });

    await user.click(screen.getByRole("button", { name: "+ Agregar una pregunta" }));
    await user.click(screen.getByRole("button", { name: "+ Agregar una pregunta" }));
    await user.click(screen.getAllByRole("button", { name: "Eliminar: Nueva pregunta" })[0]);
    await user.click(screen.getByRole("button", { name: "Guardar y probar mi agente" }));

    const questions = onSubmit.mock.calls[0][0].config.qualification_questions;
    expect(questions.map((q: { key?: string | null }) => q.key ?? null)).toEqual([
      "operation",
      "zone",
      "budget",
      "custom_3",
      null,
    ]);
    expect(questions[4]).not.toHaveProperty("id");
  });

  it("reorders questions", async () => {
    const { user } = renderForm();

    await user.click(screen.getByRole("button", { name: "Subir: Presupuesto" }));

    expect(questionLabels()).toEqual([
      "Si busca comprar o alquilar",
      "Presupuesto",
      "Zona o barrio",
    ]);
    expect(
      (screen.getByRole("button", { name: "Subir: Si busca comprar o alquilar" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("disables a question and submits the whole form", async () => {
    const { user, onSubmit } = renderForm();

    await user.click(screen.getByLabelText("Activar: Presupuesto"));
    await user.click(screen.getByRole("button", { name: "Guardar y probar mi agente" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const input = onSubmit.mock.calls[0][0];
    expect(input.config.qualification_questions.map((q: { key: string; enabled: boolean }) => [q.key, q.enabled])).toEqual([
      ["operation", true],
      ["zone", true],
      ["budget", false],
    ]);
    expect(input.notification_emails).toEqual(["duena@example.com"]);
    expect(input.business_hours).toHaveLength(5);
  });

  it("does not submit with an empty question label or email", async () => {
    const { user, onSubmit } = renderForm();

    await user.clear(screen.getByLabelText("Pregunta 2"));
    await user.click(screen.getByRole("button", { name: "Guardar y probar mi agente" }));
    expect(screen.getByText("Todas las preguntas necesitan un texto.")).toBeTruthy();

    await user.type(screen.getByLabelText("Pregunta 2"), "Zona");
    await user.clear(screen.getByLabelText("Avisarme de cada lead en"));
    await user.click(screen.getByRole("button", { name: "Guardar y probar mi agente" }));
    expect(screen.getByText("Ingresá al menos un email para los avisos.")).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("limits the list to 10 questions", async () => {
    const { user } = renderForm();
    const add = screen.getByRole("button", { name: "+ Agregar una pregunta" });

    for (let index = 0; index < 7; index += 1) {
      await user.click(add);
    }

    expect(questionLabels()).toHaveLength(10);
    expect((add as HTMLButtonElement).disabled).toBe(true);
  });

  it("is read-only for viewers", () => {
    renderForm({ readOnly: true });

    expect((screen.getByLabelText("Nombre del agente") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Pregunta 1") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Guardar y probar mi agente" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Usar lo recomendado" })).toBeNull();
    expect(screen.queryByRole("button", { name: "+ Agregar una pregunta" })).toBeNull();
    expect(within(document.body).getByText(/Solo el dueño o un encargado/)).toBeTruthy();
  });

  it("shows back and intro only in the wizard", async () => {
    const onBack = vi.fn();
    const { user } = renderForm({ onBack, showIntro: true });

    expect(screen.getByText(/Ya está todo completo con lo que mejor funciona/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "← Volver" }));
    expect(onBack).toHaveBeenCalled();
  });
});
