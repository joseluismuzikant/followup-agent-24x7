import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import { fetchReminders, saveReminderPolicy, saveTemplateText } from "../api/reminders";
import { me, reminderSettings, reminderTemplate } from "../test-fixtures";
import { RecordatoriosPage } from "./recordatorios";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/reminders", () => ({
  fetchReminders: vi.fn(),
  saveReminderPolicy: vi.fn(),
  saveTemplateText: vi.fn(),
}));
vi.mock("../api/whatsapp", () => ({
  fetchWhatsAppStatus: vi.fn().mockResolvedValue({ status: "connected" }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RecordatoriosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("RecordatoriosPage (C4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(me());
    vi.mocked(fetchReminders).mockResolvedValue(
      reminderSettings({
        templates: [
          reminderTemplate("before"),
          reminderTemplate("due", { status: "pending", status_label: "en revisión" }),
          reminderTemplate("after", {
            status: "rejected",
            status_label: "rechazada: el formato no es válido",
          }),
          reminderTemplate("several"),
        ],
      }),
    );
  });

  it("shows the sequence with each template's Meta status, the number and this month's count", async () => {
    renderPage();

    const sequence = await screen.findByRole("region", { name: "Secuencia de recordatorios" });
    const steps = within(sequence).getAllByRole("listitem");
    expect(steps).toHaveLength(4);
    expect(within(steps[0]!).getByText("aprobada")).toBeTruthy();
    expect(within(steps[1]!).getByText("en revisión")).toBeTruthy();
    expect(within(steps[2]!).getByText("rechazada: el formato no es válido")).toBeTruthy();
    expect(within(steps[3]!).getByText(/te avisamos por email/)).toBeTruthy();
    expect(screen.getByText("+54 9 11 5555-0200")).toBeTruthy();
    expect(screen.getByText("3 mensajes de recordatorio")).toBeTruthy();
    expect(screen.getByText("Muy pronto")).toBeTruthy();
    expect(screen.queryByText(/respuestas gratis/)).toBeNull();
    expect(screen.getByText(/Los próximos: 23 nov, 7 dic/)).toBeTruthy();
  });

  it("adds a step and saves the policy with a custom window", async () => {
    vi.mocked(saveReminderPolicy).mockResolvedValue(reminderSettings({ configured: true }));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "+ Agregar un paso" }));
    await user.click(screen.getByRole("radio", { name: "Personalizado" }));
    await user.clear(screen.getByLabelText("De"));
    await user.type(screen.getByLabelText("De"), "14:00");
    await user.clear(screen.getByLabelText("a"));
    await user.type(screen.getByLabelText("a"), "17:30");
    await user.click(screen.getByLabelText(/No enviar en feriados/));
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    const input = vi.mocked(saveReminderPolicy).mock.calls[0]![0];
    expect(input.steps.map((step) => step.offset_days)).toEqual([-3, 0, 7, 10, 15]);
    expect(input.steps[3]).toMatchObject({ kind: "reminder", template_kind: "after" });
    expect(input.window).toEqual({ preset: "custom", start: "14:00", end: "17:30" });
    expect(input.skip_holidays).toBe(false);
    expect(await screen.findByText("Guardamos los cambios.")).toBeTruthy();
  });

  it("says two steps cannot fall on the same day, before saving", async () => {
    const user = renderPage();

    const sequence = await screen.findByRole("region", { name: "Secuencia de recordatorios" });
    const [first] = within(sequence).getAllByRole("spinbutton");
    await user.tripleClick(first!);
    await user.keyboard("7");
    await user.selectOptions(within(sequence).getAllByRole("combobox")[0]!, "after");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(screen.getByRole("alert").textContent).toBe("Dos pasos no pueden caer el mismo día.");
    expect(saveReminderPolicy).not.toHaveBeenCalled();
  });

  it("edits a message and sends it to Meta's review", async () => {
    vi.mocked(saveTemplateText).mockResolvedValue(reminderSettings());
    const user = renderPage();

    const before = await screen.findByRole("article", { name: "Antes del vencimiento" });
    await user.click(within(before).getByRole("button", { name: "Editar texto" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar: Antes del vencimiento" });
    const text = within(dialog).getByLabelText("Texto del mensaje");
    await user.clear(text);
    await user.type(text, "Hola {{cliente}, recordá la factura {{factura}. Gracias.");
    await user.click(within(dialog).getByRole("button", { name: "Enviar a revisión de Meta" }));

    expect(saveTemplateText).toHaveBeenCalledWith(
      "before",
      "Hola {cliente}, recordá la factura {factura}. Gracias.",
    );
  });
});
