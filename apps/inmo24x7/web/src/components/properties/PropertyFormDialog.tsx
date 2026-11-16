import type {
  ConditionSettings,
  Property,
  PropertyConditions,
  PropertyInput,
} from "@followup/api-client-inmo24x7";
import { Button, Dialog, FormField, Input, SegmentedControl } from "@followup/ui";
import { useId, useState } from "react";

import { EMPTY_CONDITIONS, forOperation } from "../../lib/conditions";
import {
  type PropertyDraft,
  type PropertyDraftErrors,
  validateProperty,
} from "../../lib/properties";
import { ConditionsFields } from "./ConditionsFields";

interface PropertyFormDialogProps {
  open: boolean;
  /** Edit this property; create a new one when null. */
  property: Property | null;
  saving: boolean;
  error: string | null;
  /** The agency's "Condiciones generales" (shown where the property says nothing). */
  settings?: ConditionSettings;
  onClose: () => void;
  onSave: (input: PropertyInput) => void;
}

function toDraft(property: Property | null): PropertyDraft {
  return {
    title: property?.title ?? "",
    address: property?.address ?? "",
    operation: property?.operation ?? "rent",
    zone: property?.zone ?? "",
    price: property ? String(property.price) : "",
    currency: property?.currency ?? "ARS",
    rooms: property ? String(property.rooms) : "",
    link: property?.link ?? "",
    status: property?.status ?? "published",
  };
}

const operations = [
  { value: "rent", label: "Alquiler" },
  { value: "sale", label: "Venta" },
] as const;

const currencies = [
  { value: "ARS", label: "Pesos" },
  { value: "USD", label: "Dólares" },
] as const;

/** "Agregar una" and edit: the same rules as the import, explained field by field. */
export function PropertyFormDialog({
  open,
  property,
  saving,
  error,
  settings,
  onClose,
  onSave,
}: PropertyFormDialogProps) {
  return (
    <Dialog
      open={open}
      title={property ? "Editar propiedad" : "Agregar una propiedad"}
      onClose={onClose}
    >
      {/* Remount per property so the fields start from it. */}
      <PropertyForm
        key={property?.id ?? "new"}
        property={property}
        saving={saving}
        error={error}
        settings={settings}
        onCancel={onClose}
        onSave={onSave}
      />
    </Dialog>
  );
}

function PropertyForm({
  property,
  saving,
  error,
  settings,
  onCancel,
  onSave,
}: {
  property: Property | null;
  saving: boolean;
  error: string | null;
  settings?: ConditionSettings;
  onCancel: () => void;
  onSave: (input: PropertyInput) => void;
}) {
  const ids = {
    title: useId(),
    address: useId(),
    zone: useId(),
    price: useId(),
    rooms: useId(),
    link: useId(),
  };
  const [draft, setDraft] = useState<PropertyDraft>(() => toDraft(property));
  const [errors, setErrors] = useState<PropertyDraftErrors>({});
  const [conditions, setConditions] = useState<PropertyConditions>(
    () => property?.conditions ?? EMPTY_CONDITIONS,
  );
  const [conditionsError, setConditionsError] = useState<string | undefined>();

  function update<K extends keyof PropertyDraft>(key: K, value: PropertyDraft[K]) {
    setDraft((current) => {
      const next = { ...current, [key]: value };
      // A new property follows the usual currency of its operation until changed by hand.
      if (key === "operation" && !property) {
        next.currency = value === "sale" ? "USD" : "ARS";
      }
      return next;
    });
  }

  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const result = validateProperty(draft);
        setErrors(result.errors);
        const months = conditions.contrato_minimo_meses;
        const badMonths = months !== null && months !== undefined && (months < 1 || months > 120);
        setConditionsError(badMonths ? "Entre 1 y 120 meses." : undefined);
        if (result.input && !badMonths) {
          onSave({ ...result.input, conditions: forOperation(conditions, draft.operation) });
        }
      }}
    >
      <FormField label="Título" htmlFor={ids.title} error={errors.title}>
        <Input
          id={ids.title}
          value={draft.title}
          placeholder="2 ambientes luminoso"
          onChange={(event) => update("title", event.target.value)}
        />
      </FormField>
      <FormField label="Dirección" htmlFor={ids.address} error={errors.address}>
        <Input
          id={ids.address}
          value={draft.address}
          placeholder="Gorriti 4800"
          onChange={(event) => update("address", event.target.value)}
        />
      </FormField>
      <FormField label="Operación">
        <SegmentedControl
          ariaLabel="Operación"
          options={operations}
          value={draft.operation}
          onChange={(value) => update("operation", value)}
        />
      </FormField>
      <FormField label="Zona o barrio" htmlFor={ids.zone} error={errors.zone}>
        <Input
          id={ids.zone}
          value={draft.zone}
          placeholder="Palermo"
          onChange={(event) => update("zone", event.target.value)}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Precio" htmlFor={ids.price} error={errors.price}>
          <Input
            id={ids.price}
            inputMode="numeric"
            value={draft.price}
            placeholder="850.000"
            onChange={(event) => update("price", event.target.value)}
          />
        </FormField>
        <FormField label="Moneda">
          <SegmentedControl
            ariaLabel="Moneda"
            options={currencies}
            value={draft.currency}
            onChange={(value) => update("currency", value)}
          />
        </FormField>
      </div>
      <FormField label="Ambientes" htmlFor={ids.rooms} error={errors.rooms}>
        <Input
          id={ids.rooms}
          inputMode="numeric"
          value={draft.rooms}
          placeholder="2"
          onChange={(event) => update("rooms", event.target.value)}
        />
      </FormField>
      <FormField
        label="Link del aviso"
        htmlFor={ids.link}
        hint="La dirección completa de la publicación, por ejemplo en tu web o en un portal."
        error={errors.link}
      >
        <Input
          id={ids.link}
          type="url"
          value={draft.link}
          placeholder="https://www.tuinmobiliaria.com.ar/propiedades/..."
          onChange={(event) => update("link", event.target.value)}
        />
      </FormField>
      <section aria-label="Condiciones" className="flex flex-col gap-3 border-t pt-4">
        <div>
          <h3 className="text-sm font-semibold">Condiciones</h3>
          <p className="text-sm text-muted-foreground">
            Sofía las usa para ordenar las opciones y avisar antes de una visita. Lo que dejes en
            «No informado» nunca descarta a nadie.
          </p>
        </div>
        <ConditionsFields
          operation={draft.operation}
          value={conditions}
          onChange={setConditions}
          defaults={settings ? settings[draft.operation] : undefined}
          error={conditionsError}
        />
      </section>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "Guardando..." : "Guardar"}
        </Button>
      </div>
    </form>
  );
}
