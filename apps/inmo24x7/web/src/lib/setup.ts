import type { AgentQuestionInput, ScheduleBlock } from "@followup/api-client-inmo24x7";

export const MAX_QUESTIONS = 10;

export const businessTypes = [
  { value: "inmobiliaria", label: "Inmobiliaria" },
  { value: "red_franquicia", label: "Red o franquicia" },
  { value: "corredor", label: "Corredor/a independiente" },
  { value: "desarrolladora", label: "Desarrolladora" },
] as const;

export const tones = [
  { value: "warm", label: "Cercano" },
  { value: "professional", label: "Profesional" },
  { value: "formal", label: "Formal" },
] as const;

export type ToneValue = (typeof tones)[number]["value"];

/** Wizard steps in order. `path` is the URL segment, `id` the API step name. */
export const wizardSteps = [
  { id: "business", path: "tu-negocio", label: "Tu negocio" },
  { id: "agent", path: "tu-agente", label: "Tu agente" },
  { id: "try", path: "probalo", label: "Probalo" },
  { id: "whatsapp", path: "whatsapp", label: "WhatsApp" },
  { id: "done", path: "listo", label: "Listo" },
] as const;

export type WizardStepId = (typeof wizardSteps)[number]["id"];

export function stepIndex(id: string): number {
  return wizardSteps.findIndex((step) => step.id === id);
}

export function stepFromPath(path: string | undefined) {
  return wizardSteps.find((step) => step.path === path);
}

function block(weekday: number, opens: string, closes: string): ScheduleBlock {
  return { weekday, opens, closes };
}

function range(days: number, opens: string, closes: string): ScheduleBlock[] {
  return Array.from({ length: days }, (_, day) => block(day, opens, closes));
}

export const hoursPresets = [
  { value: "weekdays", label: "Lunes a viernes, 9 a 18", blocks: range(5, "09:00", "18:00") },
  { value: "mon_sat", label: "Lunes a sábado, 9 a 13", blocks: range(6, "09:00", "13:00") },
] as const;

export type HoursPresetValue = (typeof hoursPresets)[number]["value"];

export const defaultHours: ScheduleBlock[] = hoursPresets[0].blocks.map((item) => ({ ...item }));

function sameHours(a: readonly ScheduleBlock[], b: readonly ScheduleBlock[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** The preset matching these hours, or null when the schedule is custom. */
export function presetForHours(blocks: readonly ScheduleBlock[]): HoursPresetValue | null {
  return hoursPresets.find((preset) => sameHours(preset.blocks, blocks))?.value ?? null;
}

/** Custom questions can be deleted; a question without a key is new and not saved yet. */
export function isCustomQuestion(question: AgentQuestionInput): boolean {
  return !question.key || question.key.startsWith("custom_");
}

export function parseEmails(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((email) => email.trim())
    .filter(Boolean);
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function trialDaysLeft(trialEndsAt: string, now = new Date()): number {
  const ms = new Date(trialEndsAt).getTime() - now.getTime();
  return Math.max(0, Math.ceil(ms / 86_400_000));
}

export function canEditSetup(role: string): boolean {
  return role === "owner" || role === "manager";
}
