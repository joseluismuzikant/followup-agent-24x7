import type {
  PolicyInput,
  ReminderSettings,
  ReminderTemplate,
  StepInput,
} from "@followup/api-client-cuentas-claras";
import { Badge, Button, cn, Input, SegmentedControl } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { saveReminderPolicy } from "../api/reminders";
import { apiErrorMessage } from "../lib/api-errors";
import { shortDate } from "../lib/format";

type Window = PolicyInput["window"];
type Preset = Window["preset"];

const presets: { value: Preset; label: string }[] = [
  { value: "team", label: "Horario del equipo" },
  { value: "mornings", label: "Mañanas 9–12" },
  { value: "business_day", label: "Todo el día hábil 9–18" },
  { value: "custom", label: "Personalizado" },
];

interface DraftStep extends StepInput {
  /** A key for React (new steps have no id yet). */
  key: string;
}

export function stepWhen(offset: number): string {
  const days = Math.abs(offset);
  const count = days === 1 ? "1 día" : `${days} días`;
  if (offset < 0) {
    return `${count} antes del vencimiento`;
  }
  if (offset === 0) {
    return "El día del vencimiento";
  }
  return `${count} después del vencimiento`;
}

function templateFor(offset: number): "before" | "due" | "after" {
  return offset < 0 ? "before" : offset === 0 ? "due" : "after";
}

export function TemplateStatusBadge({ template }: { template: ReminderTemplate }) {
  const tone =
    template.status === "approved"
      ? "success"
      : template.status === "rejected" ||
          template.status === "paused" ||
          template.status === "disabled" ||
          template.status === "submit_failed"
        ? "danger"
        : template.status === "pending"
          ? "warning"
          : "neutral";
  return <Badge tone={tone}>{template.status_label}</Badge>;
}

function draftFrom(settings: ReminderSettings): DraftStep[] {
  return settings.steps.map((step) => ({
    key: step.id,
    id: step.id,
    offset_days: step.offset_days,
    kind: step.kind,
    template_kind: step.template_kind,
    active: step.active,
  }));
}

/** Problems the API would reject, said before saving. */
export function validateSteps(steps: DraftStep[]): string | null {
  const offsets = steps.map((step) => step.offset_days);
  if (offsets.some((offset) => !Number.isInteger(offset) || offset < -30 || offset > 90)) {
    return "Cada paso va entre 30 días antes y 90 días después del vencimiento.";
  }
  if (new Set(offsets).size !== offsets.length) {
    return "Dos pasos no pueden caer el mismo día.";
  }
  const escalation = steps.find((step) => step.kind === "escalate");
  if (escalation && offsets.some((offset) => offset > escalation.offset_days)) {
    return "El aviso al dueño tiene que ser el último paso.";
  }
  if (!steps.some((step) => step.kind === "reminder")) {
    return "Dejá al menos un recordatorio.";
  }
  return null;
}

export interface ReminderPolicyEditorProps {
  settings: ReminderSettings;
  canEdit: boolean;
  /** The wizard's short version: no template previews. */
  compact?: boolean;
  saveLabel?: string;
  onSaved?: (settings: ReminderSettings) => void;
}

/** C4's sequence, send window and pauses (also the wizard's "Recordatorios" step). */
export function ReminderPolicyEditor({
  settings,
  canEdit,
  compact = false,
  saveLabel = "Guardar cambios",
  onSaved,
}: ReminderPolicyEditorProps) {
  const queryClient = useQueryClient();
  const ids = { start: useId(), end: useId(), holidays: useId(), promise: useId() };
  const [steps, setSteps] = useState<DraftStep[]>(() => draftFrom(settings));
  const [window, setWindow] = useState<Window>({
    preset: settings.window.preset,
    start: settings.window.start ?? "09:00",
    end: settings.window.end ?? "12:00",
  });
  const [skipHolidays, setSkipHolidays] = useState(settings.skip_holidays);
  const [pauseOnPromise, setPauseOnPromise] = useState(settings.pause_on_promise);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const templates = new Map(settings.templates.map((template) => [template.kind, template]));

  const save = useMutation({
    mutationFn: () =>
      saveReminderPolicy({
        steps: [...steps]
          .sort((a, b) => a.offset_days - b.offset_days)
          .map((step) => ({
            id: step.id,
            offset_days: step.offset_days,
            kind: step.kind,
            active: step.active,
            template_kind: step.kind === "reminder" ? templateFor(step.offset_days) : null,
          })),
        window:
          window.preset === "custom"
            ? window
            : { preset: window.preset, start: null, end: null },
        skip_holidays: skipHolidays,
        pause_on_promise: pauseOnPromise,
      }),
    onSuccess: async (result) => {
      queryClient.setQueryData(["reminders"], result);
      setSteps(draftFrom(result));
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      onSaved?.(result);
    },
  });

  function update(key: string, changes: Partial<DraftStep>) {
    setSaved(false);
    setSteps(steps.map((step) => (step.key === key ? { ...step, ...changes } : step)));
  }

  function addStep() {
    setSaved(false);
    const used = new Set(steps.map((step) => step.offset_days));
    const reminders = steps.filter((step) => step.kind === "reminder");
    const escalation = steps.find((step) => step.kind === "escalate");
    let offset = Math.max(0, ...reminders.map((step) => step.offset_days)) + 3;
    while (used.has(offset) || (escalation && offset >= escalation.offset_days)) {
      offset = escalation && offset >= escalation.offset_days ? offset - 1 : offset + 1;
      if (offset <= -30) {
        break;
      }
    }
    setSteps([
      ...steps,
      { key: `new-${steps.length}-${offset}`, offset_days: offset, kind: "reminder", active: true },
    ]);
  }

  function submit() {
    const error = validateSteps(steps);
    setProblem(error);
    if (window.preset === "custom" && (!window.start || !window.end || window.start >= window.end)) {
      setProblem("El horario personalizado tiene que empezar antes de terminar.");
      return;
    }
    if (!error) {
      save.mutate();
    }
  }

  const ordered = [...steps].sort((a, b) => a.offset_days - b.offset_days);

  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Secuencia de recordatorios" className="flex flex-col gap-3">
        <ol className="flex flex-col gap-3">
          {ordered.map((step) => {
            const template =
              step.kind === "reminder" ? templates.get(templateFor(step.offset_days)) : undefined;
            return (
              <li
                key={step.key}
                className={cn(
                  "flex flex-col gap-3 rounded-lg border p-3 sm:p-4",
                  step.active ? "bg-card" : "bg-muted/40 opacity-80",
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <StepWhen step={step} disabled={!canEdit} onChange={(offset) => update(step.key, { offset_days: offset })} />
                  <div className="flex flex-wrap items-center gap-3">
                    {template ? <TemplateStatusBadge template={template} /> : null}
                    <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-0">
                      <input
                        type="checkbox"
                        checked={step.active ?? true}
                        disabled={!canEdit}
                        onChange={(event) => update(step.key, { active: event.target.checked })}
                      />
                      Activo
                    </label>
                    {canEdit && step.kind === "reminder" && steps.length > 1 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={`Quitar el paso ${stepWhen(step.offset_days)}`}
                        onClick={() => {
                          setSaved(false);
                          setSteps(steps.filter((item) => item.key !== step.key));
                        }}
                      >
                        Quitar
                      </Button>
                    ) : null}
                  </div>
                </div>
                {step.kind === "escalate" ? (
                  <p className="text-sm text-muted-foreground">
                    No le escribimos más al cliente: frenamos los recordatorios de esa factura y
                    te avisamos por email para que la sigas vos.
                  </p>
                ) : compact ? null : template ? (
                  <p className="whitespace-pre-line rounded-md bg-muted/50 p-3 text-sm">
                    {template.preview}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ol>
        {canEdit ? (
          <Button type="button" variant="outline" className="self-start" onClick={addStep}>
            + Agregar un paso
          </Button>
        ) : null}
      </section>

      <section aria-label="Horario de envío" className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Horario de envío</h3>
        <SegmentedControl
          ariaLabel="Horario de envío"
          options={presets}
          value={window.preset}
          disabled={!canEdit}
          className="flex-wrap"
          onChange={(preset) => {
            setSaved(false);
            setWindow({ ...window, preset });
          }}
        />
        {window.preset === "custom" ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label htmlFor={ids.start}>De</label>
            <Input
              id={ids.start}
              type="time"
              className="w-32"
              min="06:00"
              max="22:00"
              value={window.start ?? ""}
              disabled={!canEdit}
              onChange={(event) => setWindow({ ...window, start: event.target.value })}
            />
            <label htmlFor={ids.end}>a</label>
            <Input
              id={ids.end}
              type="time"
              className="w-32"
              min="06:00"
              max="22:00"
              value={window.end ?? ""}
              disabled={!canEdit}
              onChange={(event) => setWindow({ ...window, end: event.target.value })}
            />
          </div>
        ) : null}
        <p className="text-sm text-muted-foreground">
          Solo de lunes a viernes, en el horario de tu negocio. Si un recordatorio cae fuera,
          sale el siguiente día hábil.
        </p>
      </section>

      <section aria-label="Pausas" className="flex flex-col gap-3 text-sm">
        <label htmlFor={ids.holidays} className="flex items-start gap-2">
          <input
            id={ids.holidays}
            type="checkbox"
            className="mt-1"
            checked={skipHolidays}
            disabled={!canEdit}
            onChange={(event) => {
              setSaved(false);
              setSkipHolidays(event.target.checked);
            }}
          />
          <span>
            <span className="block font-medium">No enviar en feriados</span>
            <span className="text-muted-foreground">
              Feriados nacionales de Argentina.
              {settings.upcoming_holidays.length
                ? ` Los próximos: ${settings.upcoming_holidays.map(shortDate).join(", ")}.`
                : ""}
            </span>
          </span>
        </label>
        <label htmlFor={ids.promise} className="flex items-start gap-2">
          <input
            id={ids.promise}
            type="checkbox"
            className="mt-1"
            checked={pauseOnPromise}
            disabled={!canEdit}
            onChange={(event) => {
              setSaved(false);
              setPauseOnPromise(event.target.checked);
            }}
          />
          <span>
            <span className="block font-medium">Pausar si el cliente prometió pagar</span>
            <span className="text-muted-foreground">
              Hasta la fecha que prometió; al día siguiente sigue la secuencia.
            </span>
          </span>
        </label>
      </section>

      {problem || save.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {problem ?? apiErrorMessage(save.error, "No pudimos guardar los cambios.")}
        </p>
      ) : null}
      {saved && !compact ? (
        <p className="text-sm text-emerald-700" role="status">
          Guardamos los cambios.
        </p>
      ) : null}
      {canEdit ? (
        <Button type="button" className="self-start" disabled={save.isPending} onClick={submit}>
          {save.isPending ? "Guardando..." : saveLabel}
        </Button>
      ) : null}
    </div>
  );
}

function StepWhen({
  step,
  disabled,
  onChange,
}: {
  step: DraftStep;
  disabled: boolean;
  onChange: (offset: number) => void;
}) {
  const id = useId();
  const days = Math.abs(step.offset_days);
  const direction = step.offset_days < 0 ? "before" : step.offset_days > 0 ? "after" : "on";
  const title = step.kind === "escalate" ? "Avisar al dueño" : "Recordatorio";

  function set(nextDays: number, nextDirection: string) {
    if (nextDirection === "on") {
      onChange(0);
      return;
    }
    const value = Math.max(1, nextDays);
    onChange(nextDirection === "before" ? -value : value);
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="font-semibold">{title}</span>
      {direction !== "on" ? (
        <>
          <label htmlFor={id} className="sr-only">
            Días
          </label>
          <Input
            id={id}
            type="number"
            min={1}
            max={direction === "before" ? 30 : 90}
            className="w-20"
            value={days}
            disabled={disabled}
            onChange={(event) => set(Number(event.target.value), direction)}
          />
          <span>{days === 1 ? "día" : "días"}</span>
        </>
      ) : null}
      <select
        aria-label={`Cuándo: ${stepWhen(step.offset_days)}`}
        className="h-10 rounded-md border bg-card px-2 text-sm"
        value={direction}
        disabled={disabled || step.kind === "escalate"}
        onChange={(event) => set(days || 1, event.target.value)}
      >
        <option value="before">antes del vencimiento</option>
        <option value="on">el día del vencimiento</option>
        <option value="after">después del vencimiento</option>
      </select>
    </div>
  );
}
