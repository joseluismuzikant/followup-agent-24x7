/** Business settings every product edits the same way: team hours and alert emails. */

export interface ScheduleBlock {
  weekday: number;
  opens: string;
  closes: string;
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

export function parseEmails(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((email) => email.trim())
    .filter(Boolean);
}

export function trialDaysLeft(trialEndsAt: string, now = new Date()): number {
  const ms = new Date(trialEndsAt).getTime() - now.getTime();
  return Math.max(0, Math.ceil(ms / 86_400_000));
}
