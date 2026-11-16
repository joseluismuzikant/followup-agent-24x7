import type { ConditionSettings, PropertyConditions } from "@followup/api-client-inmo24x7";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  SegmentedControl,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { fetchConditionSettings, saveConditionSettings } from "../../api/properties";
import { apiErrorMessage } from "../../lib/api-errors";
import { type Operation, forOperation } from "../../lib/conditions";
import { ConditionsFields } from "./ConditionsFields";

const OPERATIONS = [
  { value: "rent", label: "Alquiler" },
  { value: "sale", label: "Venta" },
] as const;

/** Configuración → "Condiciones generales": the agency's defaults per operation (a
 * property's own value wins) and how Sofía uses the conditions. */
export function ConditionSettingsCard({ readOnly }: { readOnly: boolean }) {
  const query = useQuery({ queryKey: ["condition-settings"], queryFn: fetchConditionSettings });
  return (
    <Card id="condiciones">
      <CardHeader>
        <CardTitle>Condiciones generales</CardTitle>
        <CardDescription>
          Lo que suele pedir tu inmobiliaria. Se aplica a cada propiedad que no diga otra cosa.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.data ? (
          // Mounted once with the loaded settings; after a save the form already holds them.
          <ConditionSettingsForm settings={query.data} readOnly={readOnly} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function Switch({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex items-start gap-2 text-sm">
      <input
        id={id}
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <span className="block font-medium">{label}</span>
        <span className="text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}

function ConditionSettingsForm({
  settings,
  readOnly,
}: {
  settings: ConditionSettings;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [operation, setOperation] = useState<Operation>("rent");
  const [rent, setRent] = useState<PropertyConditions>(settings.rent);
  const [sale, setSale] = useState<PropertyConditions>(settings.sale);
  const [warn, setWarn] = useState(settings.warn_before_visit);
  const [alternatives, setAlternatives] = useState(settings.offer_alternatives);
  const [notify, setNotify] = useState(settings.notify_mismatches);
  const save = useMutation({
    mutationFn: () =>
      saveConditionSettings({
        rent: forOperation(rent, "rent"),
        sale: forOperation(sale, "sale"),
        warn_before_visit: warn,
        offer_alternatives: alternatives,
        notify_mismatches: notify,
      }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(["condition-settings"], saved);
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
    },
  });

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (!readOnly) {
          save.mutate();
        }
      }}
    >
      <section aria-label="Valores por defecto" className="flex flex-col gap-3">
        <SegmentedControl
          ariaLabel="Operación"
          options={OPERATIONS}
          value={operation}
          onChange={setOperation}
        />
        <fieldset disabled={readOnly} className="flex flex-col gap-3">
          {operation === "rent" ? (
            <ConditionsFields operation="rent" value={rent} onChange={setRent} showText={false} />
          ) : (
            <ConditionsFields operation="sale" value={sale} onChange={setSale} showText={false} />
          )}
        </fieldset>
      </section>
      <section aria-label="Cómo las usa Sofía" className="flex flex-col gap-3 border-t pt-4">
        <h3 className="text-sm font-semibold">Cómo las usa Sofía</h3>
        <Switch
          label="Avisar los requisitos antes de coordinar una visita"
          hint="Si la persona no cumple un requisito, Sofía se lo dice con amabilidad y le pregunta si podría cumplirlo."
          checked={warn}
          disabled={readOnly}
          onChange={setWarn}
        />
        <Switch
          label="Ofrecer otras condiciones si nada encaja"
          hint="Si todas las opciones piden lo mismo (por ejemplo, contrato de 2 años), Sofía pregunta una vez si le interesan igual."
          checked={alternatives}
          disabled={readOnly}
          onChange={setAlternatives}
        />
        <Switch
          label="Notificar al equipo las consultas que no cumplen"
          hint="Con «No», las que no cumplen lo que eligieron no llegan por email: quedan en Consultas, marcadas «No cumple»."
          checked={notify}
          disabled={readOnly}
          onChange={setNotify}
        />
      </section>
      {save.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(save.error, "No pudimos guardar las condiciones.")}
        </p>
      ) : null}
      {save.isSuccess ? (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          Condiciones guardadas.
        </p>
      ) : null}
      {readOnly ? (
        <p className="text-sm text-muted-foreground">
          Solo el dueño o un encargado pueden cambiarlas.
        </p>
      ) : (
        <Button type="submit" className="self-start" disabled={save.isPending}>
          {save.isPending ? "Guardando..." : "Guardar condiciones"}
        </Button>
      )}
    </form>
  );
}
