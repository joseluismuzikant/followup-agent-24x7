import type { AgentQuestionInput } from "@followup/api-client-inmo24x7";

export {
  defaultHours,
  hoursPresets,
  parseEmails,
  presetForHours,
  trialDaysLeft,
  type HoursPresetValue,
} from "@followup/app-shell";

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

/** Custom questions can be deleted; a question without a key is new and not saved yet. */
export function isCustomQuestion(question: AgentQuestionInput): boolean {
  return !question.key || question.key.startsWith("custom_");
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export { canEditSetup } from "@followup/app-shell";
