import type { TenantSettings } from "@followup/api-client-inmo24x7";
import { Button, FormField, Input } from "@followup/ui";
import { useState } from "react";
import type { FormEvent } from "react";

import { businessTypes } from "../../lib/setup";

interface BusinessStepProps {
  /** Present when the business already exists and the step is being revisited. */
  existing?: TenantSettings;
  saving: boolean;
  error: string | null;
  onSubmit: (businessName: string, businessType: string) => void;
}

export function BusinessStep({ existing, saving, error, onSubmit }: BusinessStepProps) {
  const [name, setName] = useState(existing?.business_name ?? "");
  const [type, setType] = useState(existing?.business_type ?? "inmobiliaria");
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setLocalError("Ingresá el nombre de tu negocio.");
      return;
    }
    setLocalError(null);
    onSubmit(name.trim(), type);
  }

  const shownError = localError ?? error;

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <FormField label="Nombre del negocio" htmlFor="business-name">
        <Input
          id="business-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Inmobiliaria Sur"
        />
      </FormField>
      <FormField label="Tipo de negocio" htmlFor="business-type">
        <select
          id="business-type"
          value={type}
          onChange={(event) => setType(event.target.value)}
          className="h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
        >
          {businessTypes.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FormField>
      {shownError ? (
        <p className="text-sm text-destructive" role="alert">
          {shownError}
        </p>
      ) : null}
      <Button type="submit" disabled={saving} className="self-start">
        {saving ? "Guardando..." : "Guardar y continuar"}
      </Button>
    </form>
  );
}
