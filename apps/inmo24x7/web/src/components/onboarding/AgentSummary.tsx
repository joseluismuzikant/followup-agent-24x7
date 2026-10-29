import type { AgentSetup } from "@followup/api-client-inmo24x7";

import { hoursPresets, presetForHours, tones } from "../../lib/setup";

export function AgentSummary({ setup }: { setup: AgentSetup }) {
  const tone = tones.find((item) => item.value === setup.config.tone)?.label;
  const preset = presetForHours(setup.business_hours);
  const hours = hoursPresets.find((item) => item.value === preset)?.label ?? "Personalizado";
  const enabled = setup.config.qualification_questions.filter((question) => question.enabled);

  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
      <dt className="text-muted-foreground">Agente</dt>
      <dd>{setup.config.agent_name}</dd>
      <dt className="text-muted-foreground">Tono</dt>
      <dd>{tone}</dd>
      <dt className="text-muted-foreground">Preguntas</dt>
      <dd>
        <ul className="list-disc pl-4">
          {enabled.map((question) => (
            <li key={question.key}>{question.label}</li>
          ))}
        </ul>
      </dd>
      <dt className="text-muted-foreground">Horario del equipo</dt>
      <dd>{hours}</dd>
      <dt className="text-muted-foreground">Avisos a</dt>
      <dd>{setup.notification_emails.join(", ")}</dd>
    </dl>
  );
}
