import type { LeadConditions, LeadDetail } from "@followup/api-client-inmo24x7";
import { Badge, Button } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { overrideConditions } from "../../api/leads";
import { apiErrorMessage } from "../../lib/api-errors";
import { STATUS_LABELS, STATUS_TONES } from "../../lib/conditions";

/** "Condiciones": what the lead said about their situation and, per property they saw,
 * "Cumple" / "No cumple: pide caución" / "Sin datos", as the agent knew it. The team can
 * override ("Cumple igual"). */
export function ConditionsBlock({
  leadId,
  conditions,
  canAct,
}: {
  leadId: string;
  conditions: LeadConditions;
  canAct: boolean;
}) {
  const queryClient = useQueryClient();
  const override = useMutation({
    mutationFn: ({ property, status }: { property: string; status: "cumple" | null }) =>
      overrideConditions(leadId, property, status),
    onSuccess: async (detail: LeadDetail) => {
      queryClient.setQueryData(["lead", leadId], detail);
      await queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
  });
  if (!conditions.facts.length && !conditions.properties.length) {
    return null;
  }

  return (
    <section aria-label="Condiciones" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Condiciones</h3>
        {conditions.status ? (
          <Badge tone={STATUS_TONES[conditions.status]}>{STATUS_LABELS[conditions.status]}</Badge>
        ) : null}
      </div>
      {conditions.facts.length ? (
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
          {conditions.facts.map((fact) => (
            <div key={fact.key} className="contents">
              <dt className="text-muted-foreground">{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">Todavía no contó su situación.</p>
      )}
      {conditions.properties.length ? (
        <ul aria-label="Propiedades vistas" className="flex flex-col gap-2">
          {conditions.properties.map((item) => (
            <li key={item.property_id} className="flex flex-col gap-1 rounded-md border p-3 text-sm">
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 font-medium">
                  {item.address}
                  {item.chosen ? (
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      (la eligió)
                    </span>
                  ) : null}
                </span>
                {item.status ? (
                  <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
                ) : null}
              </span>
              <span className="text-muted-foreground">{item.summary}</span>
              {item.features.length ? (
                <span className="text-emerald-700">Coincide: {item.features.join(", ")}</span>
              ) : null}
              {item.notes.length ? (
                <span className="text-muted-foreground">Ojo: {item.notes.join(", ")}</span>
              ) : null}
              {canAct && item.agent_status === "no_cumple" ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="self-start"
                  disabled={override.isPending}
                  onClick={() =>
                    override.mutate({
                      property: item.property_id,
                      status: item.overridden ? null : "cumple",
                    })
                  }
                >
                  {item.overridden ? "Volver a lo que vio el agente" : "Cumple igual"}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {override.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(override.error, "No pudimos guardar el cambio.")}
        </p>
      ) : null}
    </section>
  );
}
