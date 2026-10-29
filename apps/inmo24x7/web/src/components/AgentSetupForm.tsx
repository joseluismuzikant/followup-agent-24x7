import type {
  AgentConfig,
  AgentQuestion,
  AgentSetup,
  AgentSetupInput,
  ScheduleBlock,
} from "@followup/api-client-inmo24x7";
import { Button, FormField, Input, SegmentedControl } from "@followup/ui";
import { useId, useState } from "react";
import type { ReactNode } from "react";

import {
  defaultHours,
  isCustomQuestion,
  MAX_QUESTIONS,
  nextCustomKey,
  parseEmails,
  tones,
} from "../lib/setup";
import { NotificationEmailsField } from "./NotificationEmailsField";
import { TeamHoursField } from "./TeamHoursField";

interface AgentSetupFormProps {
  setup: AgentSetup;
  businessName: string;
  submitLabel: string;
  onSubmit: (input: AgentSetupInput) => void;
  saving?: boolean;
  /** Error from the last save attempt, already in Spanish. */
  error?: string | null;
  readOnly?: boolean;
  onBack?: () => void;
  showIntro?: boolean;
}

/** The agent form shared by wizard step 2 and the Agente page. */
export function AgentSetupForm({
  setup,
  businessName,
  submitLabel,
  onSubmit,
  saving = false,
  error = null,
  readOnly = false,
  onBack,
  showIntro = false,
}: AgentSetupFormProps) {
  const nameId = useId();
  const [config, setConfig] = useState<AgentConfig>(setup.config);
  const [hours, setHours] = useState<ScheduleBlock[]>(setup.business_hours);
  const [emails, setEmails] = useState(setup.notification_emails.join(", "));
  const [localError, setLocalError] = useState<string | null>(null);

  const questions = config.qualification_questions;

  function updateQuestions(next: AgentQuestion[]) {
    setConfig({ ...config, qualification_questions: next });
  }

  function updateQuestion(index: number, changes: Partial<AgentQuestion>) {
    updateQuestions(
      questions.map((question, position) =>
        position === index ? { ...question, ...changes } : question,
      ),
    );
  }

  function move(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= questions.length) {
      return;
    }
    const next = [...questions];
    [next[index], next[target]] = [next[target], next[index]];
    updateQuestions(next);
  }

  function addQuestion() {
    updateQuestions([
      ...questions,
      {
        key: nextCustomKey(questions),
        label: "Nueva pregunta",
        kind: "text",
        options: [],
        enabled: true,
      },
    ]);
  }

  function useRecommended() {
    setConfig(setup.defaults);
    setHours(defaultHours.map((item) => ({ ...item })));
    setLocalError(null);
  }

  function submit() {
    if (!config.agent_name.trim()) {
      setLocalError("Ponele un nombre a tu agente.");
      return;
    }
    if (questions.some((question) => !question.label.trim())) {
      setLocalError("Todas las preguntas necesitan un texto.");
      return;
    }
    const notificationEmails = parseEmails(emails);
    if (notificationEmails.length === 0) {
      setLocalError("Ingresá al menos un email para los avisos.");
      return;
    }
    setLocalError(null);
    onSubmit({ config, business_hours: hours, notification_emails: notificationEmails });
  }

  const shownError = localError ?? error;
  const agentName = config.agent_name.trim() || "tu agente";

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (!readOnly) {
          submit();
        }
      }}
    >
      {showIntro ? (
        <p className="text-sm text-muted-foreground">
          Ya está todo completo con lo que mejor funciona para inmobiliarias. Cambiá lo que
          quieras o seguí con esto.
        </p>
      ) : null}

      <FormField label="Nombre del agente" htmlFor={nameId}>
        <Input
          id={nameId}
          value={config.agent_name}
          disabled={readOnly}
          onChange={(event) => setConfig({ ...config, agent_name: event.target.value })}
        />
        <p className="text-sm italic text-muted-foreground" aria-live="polite">
          «Hola, soy {agentName}, de {businessName}»
        </p>
      </FormField>

      <FormField label="Tono">
        <SegmentedControl
          ariaLabel="Tono"
          options={tones}
          value={config.tone}
          disabled={readOnly}
          onChange={(tone) => setConfig({ ...config, tone })}
        />
      </FormField>

      <FormField
        label="Qué le pregunta tu agente a cada persona"
        hint="De a una pregunta por mensaje, y siempre después de mostrarle opciones."
      >
        <ul className="flex flex-col gap-2">
          {questions.map((question, index) => (
            <li key={question.key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={question.enabled}
                disabled={readOnly}
                aria-label={`Activar: ${question.label}`}
                onChange={(event) => updateQuestion(index, { enabled: event.target.checked })}
              />
              <Input
                value={question.label}
                disabled={readOnly}
                aria-label={`Pregunta ${index + 1}`}
                onChange={(event) => updateQuestion(index, { label: event.target.value })}
              />
              {readOnly ? null : (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={index === 0}
                    aria-label={`Subir: ${question.label}`}
                    onClick={() => move(index, -1)}
                  >
                    ↑
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={index === questions.length - 1}
                    aria-label={`Bajar: ${question.label}`}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </Button>
                  {isCustomQuestion(question) ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Eliminar: ${question.label}`}
                      onClick={() => updateQuestions(questions.filter((_, i) => i !== index))}
                    >
                      Eliminar
                    </Button>
                  ) : null}
                </>
              )}
            </li>
          ))}
        </ul>
        {readOnly ? null : (
          <Button
            type="button"
            variant="link"
            className="self-start px-0"
            disabled={questions.length >= MAX_QUESTIONS}
            onClick={addQuestion}
          >
            + Agregar una pregunta
          </Button>
        )}
      </FormField>

      <TeamHoursField value={hours} onChange={setHours} disabled={readOnly} />

      <NotificationEmailsField
        label="Avisarme de cada lead en"
        value={emails}
        onChange={setEmails}
        disabled={readOnly}
      />

      <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
        Fuera de horario, tu agente sigue respondiendo y propone una visita para que tu equipo
        la confirme.
      </p>

      {shownError ? (
        <p className="text-sm text-destructive" role="alert">
          {shownError}
        </p>
      ) : null}

      {readOnly ? (
        <p className="text-sm text-muted-foreground">
          Solo el dueño o un encargado pueden cambiar esta configuración.
        </p>
      ) : (
        <FormActions>
          {onBack ? (
            <Button type="button" variant="ghost" onClick={onBack}>
              ← Volver
            </Button>
          ) : null}
          <Button type="button" variant="outline" onClick={useRecommended}>
            Usar lo recomendado
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Guardando..." : submitLabel}
          </Button>
        </FormActions>
      )}
    </form>
  );
}

function FormActions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}
