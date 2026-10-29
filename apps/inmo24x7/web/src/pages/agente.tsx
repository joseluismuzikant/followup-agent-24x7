import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchAgentSetup, fetchAgentVersions, saveAgentSetup } from "../api/agent-setup";
import { fetchMe } from "../api/me";
import { AgentSetupForm } from "../components/AgentSetupForm";
import { apiErrorMessage } from "../lib/api-errors";
import { canEditSetup, formatDate } from "../lib/setup";

export function AgentePage() {
  const queryClient = useQueryClient();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const setupQuery = useQuery({ queryKey: ["agent-setup"], queryFn: fetchAgentSetup });
  const versionsQuery = useQuery({
    queryKey: ["agent-versions"],
    queryFn: fetchAgentVersions,
  });
  const mutation = useMutation({
    mutationFn: saveAgentSetup,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-setup"] });
      await queryClient.invalidateQueries({ queryKey: ["agent-versions"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
  });

  const setup = setupQuery.data;
  const me = meQuery.data;
  if (!setup || !me) {
    return null;
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Tu agente</CardTitle>
          <CardDescription>
            {setup.version > 0 && setup.updated_at
              ? `Versión ${setup.version} · actualizada ${formatDate(setup.updated_at)}`
              : "Todavía no guardaste cambios. Estás usando lo recomendado."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <AgentSetupForm
            key={setup.version}
            setup={setup}
            businessName={me.tenant.name}
            readOnly={!canEditSetup(me.profile.role)}
            submitLabel="Guardar cambios"
            saving={mutation.isPending}
            error={
              mutation.isError
                ? apiErrorMessage(mutation.error, "No pudimos guardar los cambios. Probá de nuevo.")
                : null
            }
            onSubmit={(input) => mutation.mutate(input)}
          />
          {mutation.isSuccess ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Cambios guardados. Tu agente los usa desde la próxima conversación.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <details className="rounded-xl border bg-card px-6 py-4">
        <summary className="cursor-pointer text-sm font-semibold">Historial de versiones</summary>
        <ul className="mt-3 flex flex-col gap-2 text-sm">
          {(versionsQuery.data ?? []).map((version) => (
            <li key={version.version} className="flex justify-between gap-4">
              <span>Versión {version.version}</span>
              <span className="text-muted-foreground">
                {formatDate(version.created_at)}
                {version.author_email ? ` · ${version.author_email}` : ""}
              </span>
            </li>
          ))}
          {versionsQuery.data?.length === 0 ? (
            <li className="text-muted-foreground">Todavía no hay versiones guardadas.</li>
          ) : null}
        </ul>
      </details>
    </div>
  );
}
