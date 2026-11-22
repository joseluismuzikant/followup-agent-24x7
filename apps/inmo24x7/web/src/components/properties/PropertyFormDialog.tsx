import type {
  PropertyChanges,
  ConditionSettings,
  ListingDraft,
  ListingFieldChange,
  Property,
  PropertyConditions,
  PropertyInput,
} from "@followup/api-client-inmo24x7";
import { Button, Dialog, FormField, Input, SegmentedControl } from "@followup/ui";
import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { refreshFromLink } from "../../api/properties";
import { apiErrorMessage } from "../../lib/api-errors";
import { EMPTY_CONDITIONS, forOperation } from "../../lib/conditions";
import {
  changeValue,
  conditionsByModel,
  draftPrice,
  fieldLabels,
  readByModel,
} from "../../lib/listing";
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
  /** A new property read from its publication ("Cargar desde un link"): the form starts
   * from it, and what the model read is marked "Revisá este dato". */
  listing?: ListingDraft | null;
  onClose: () => void;
  onSave: (input: PropertyInput | PropertyChanges) => void;
}

const REVIEW = "Revisá este dato: lo leímos del texto de la publicación.";

function toDraft(property: Property | null, listing?: ListingDraft | null): PropertyDraft {
  if (!property && listing) {
    const operation = listing.operation ?? "rent";
    return {
      title: listing.title,
      address: listing.address,
      operation,
      zone: listing.zone,
      price: listing.price ? String(listing.price) : "",
      currency: listing.currency ?? (operation === "sale" ? "USD" : "ARS"),
      rooms: listing.rooms ? String(listing.rooms) : "",
      link: listing.link,
      status: listing.status ?? "published",
    };
  }
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
  listing,
  onClose,
  onSave,
}: PropertyFormDialogProps) {
  const fromListing = !property && listing ? listing : null;
  return (
    <Dialog
      open={open}
      title={
        property ? "Editar propiedad" : fromListing ? "Revisá la propiedad" : "Agregar una propiedad"
      }
      onClose={onClose}
    >
      {/* Remount per property (or publication read) so the fields start from it. */}
      <PropertyForm
        key={property?.id ?? (fromListing ? `link:${fromListing.link}` : "new")}
        property={property}
        listing={fromListing}
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
  listing,
  saving,
  error,
  settings,
  onCancel,
  onSave,
}: {
  property: Property | null;
  listing: ListingDraft | null;
  saving: boolean;
  error: string | null;
  settings?: ConditionSettings;
  onCancel: () => void;
  onSave: (input: PropertyInput | PropertyChanges) => void;
}) {
  const ids = {
    title: useId(),
    address: useId(),
    zone: useId(),
    price: useId(),
    rooms: useId(),
    link: useId(),
  };
  const [draft, setDraft] = useState<PropertyDraft>(() => toDraft(property, listing));
  const [errors, setErrors] = useState<PropertyDraftErrors>({});
  const [conditions, setConditions] = useState<PropertyConditions>(
    () => property?.conditions ?? listing?.conditions ?? EMPTY_CONDITIONS,
  );
  const review = (field: string) => (readByModel(listing, field) ? REVIEW : undefined);
  const [conditionsError, setConditionsError] = useState<string | undefined>();
  const external = property?.source === "tokko";

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
        if (external) {
          // Tokko's fields are edited in Tokko: only the conditions are ours.
          const months = conditions.contrato_minimo_meses;
          const badMonths =
            months !== null && months !== undefined && (months < 1 || months > 120);
          setConditionsError(badMonths ? "Entre 1 y 120 meses." : undefined);
          if (!badMonths) {
            onSave({ conditions: forOperation(conditions, draft.operation) });
          }
          return;
        }
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
      {listing ? <ListingPreview listing={listing} /> : null}
      {property && !external ? (
        <RefreshFromLink
          property={property}
          onApply={(change) => {
            const value = change.read;
            setDraft((current) => ({
              ...current,
              [change.field]:
                change.field === "price" || change.field === "rooms" ? String(value) : value,
            }));
          }}
        />
      ) : null}
      {external && property ? (
        <TokkoSummary property={property} />
      ) : (
        <>
      <FormField
        label="Título"
        htmlFor={ids.title}
        hint={review("title")}
        error={errors.title}
      >
        <Input
          id={ids.title}
          value={draft.title}
          placeholder="2 ambientes luminoso"
          onChange={(event) => update("title", event.target.value)}
        />
      </FormField>
      <FormField
        label="Dirección"
        htmlFor={ids.address}
        hint={review("address")}
        error={errors.address}
      >
        <Input
          id={ids.address}
          value={draft.address}
          placeholder="Gorriti 4800"
          onChange={(event) => update("address", event.target.value)}
        />
      </FormField>
      <FormField label="Operación" hint={review("operation")}>
        <SegmentedControl
          ariaLabel="Operación"
          options={operations}
          value={draft.operation}
          onChange={(value) => update("operation", value)}
        />
      </FormField>
      <FormField
        label="Zona o barrio"
        htmlFor={ids.zone}
        hint={review("zone")}
        error={errors.zone}
      >
        <Input
          id={ids.zone}
          value={draft.zone}
          placeholder="Palermo"
          onChange={(event) => update("zone", event.target.value)}
        />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
        label="Precio"
        htmlFor={ids.price}
        hint={review("price")}
        error={errors.price}
      >
          <Input
            id={ids.price}
            inputMode="numeric"
            value={draft.price}
            placeholder="850.000"
            onChange={(event) => update("price", event.target.value)}
          />
        </FormField>
        <FormField label="Moneda" hint={review("currency")}>
          <SegmentedControl
            ariaLabel="Moneda"
            options={currencies}
            value={draft.currency}
            onChange={(value) => update("currency", value)}
          />
        </FormField>
      </div>
      <FormField
        label="Ambientes"
        htmlFor={ids.rooms}
        hint={review("rooms")}
        error={errors.rooms}
      >
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
        </>
      )}
      <section aria-label="Condiciones" className="flex flex-col gap-3 border-t pt-4">
        <div>
          <h3 className="text-sm font-semibold">Condiciones</h3>
          <p className="text-sm text-muted-foreground">
            Sofía las usa para ordenar las opciones y avisar antes de una visita. Lo que dejes en
            «No informado» nunca descarta a nadie.
          </p>
          {conditionsByModel(listing) ? (
            <p className="mt-1 text-sm text-amber-700">
              Revisá las condiciones: algunas las leímos del texto de la publicación.
            </p>
          ) : null}
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


/** A Tokko listing: its data as Tokko has it, with where to change it. */
function TokkoSummary({ property }: { property: Property }) {
  const rows: [string, string][] = [
    ["Título", property.title],
    ["Dirección", property.address],
    ["Operación", property.operation === "sale" ? "Venta" : "Alquiler"],
    ["Zona", property.zone],
    ["Precio", `${property.currency} ${property.price.toLocaleString("es-AR")}`],
    ["Ambientes", String(property.rooms)],
  ];
  return (
    <section aria-label="Datos de Tokko" className="flex flex-col gap-3 rounded-lg border bg-muted p-3">
      <p className="text-sm font-medium">
        Se edita en Tokko
        {property.external_ref ? (
          <span className="font-normal text-muted-foreground"> · código {property.external_ref}</span>
        ) : null}
      </p>
      <p className="text-sm text-muted-foreground">
        Estos datos vienen de Tokko y se actualizan solos. Acá podés cambiar sus condiciones.
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <a
        className="text-sm text-brand underline-offset-4 hover:underline"
        href={property.link}
        target="_blank"
        rel="noreferrer"
      >
        Ver la publicación
      </a>
    </section>
  );
}

/** What was read from the publication: its cover (for the preview only), title and price,
 * and why something could not be read. */
function ListingPreview({ listing }: { listing: ListingDraft }) {
  const price = draftPrice(listing);
  return (
    <section
      aria-label="Publicación leída"
      className="flex flex-col gap-3 rounded-lg border bg-muted/40 p-3"
    >
      {listing.title || price || listing.image_url ? (
        <div className="flex gap-3">
          {listing.image_url ? (
            <img
              src={listing.image_url}
              alt=""
              referrerPolicy="no-referrer"
              className="h-20 w-24 shrink-0 rounded-md object-cover"
            />
          ) : null}
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm font-semibold leading-tight break-words">
              {listing.title || "Sin título"}
            </span>
            {price ? <span className="text-sm">{price}</span> : null}
            {listing.floor_area_m2 ? (
              <span className="text-xs text-muted-foreground">{listing.floor_area_m2} m²</span>
            ) : null}
          </div>
        </div>
      ) : null}
      {listing.message ? (
        <p className="text-sm" role="status">
          {listing.message}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Revisá los datos antes de guardar. Nada se guarda hasta que toques «Guardar».
        </p>
      )}
      {listing.warnings.map((warning) => (
        <p key={warning} className="text-sm text-amber-700">
          {warning}
        </p>
      ))}
    </section>
  );
}

/** "Actualizar desde el link": re-read the publication (or its pasted text) and apply what
 * changed, field by field, to the form. Saving stays the agent's. */
function RefreshFromLink({
  property,
  onApply,
}: {
  property: Property;
  onApply: (change: ListingFieldChange) => void;
}) {
  const textId = useId();
  const [text, setText] = useState("");
  const [applied, setApplied] = useState<string[]>([]);
  const refresh = useMutation({
    mutationFn: (pasted?: string) => refreshFromLink(property.id, pasted),
    onMutate: () => setApplied([]),
  });
  const result = refresh.data;
  const blocked = result?.draft.problem === "blocked";
  return (
    <section aria-label="Actualizar desde el link" className="flex flex-col gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        disabled={refresh.isPending}
        onClick={() => refresh.mutate(undefined)}
      >
        {refresh.isPending ? "Leyendo la publicación..." : "Actualizar desde el link"}
      </Button>
      {refresh.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(refresh.error, "No pudimos leer la publicación. Probá de nuevo.")}
        </p>
      ) : null}
      {result?.draft.message ? (
        <p className="text-sm" role="status">
          {result.draft.message}
        </p>
      ) : null}
      {blocked ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={textId} className="text-sm font-medium">
            Texto de la publicación
          </label>
          <textarea
            id={textId}
            rows={5}
            value={text}
            className="rounded-md border bg-card p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            onChange={(event) => setText(event.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="self-start"
            disabled={refresh.isPending || !text.trim()}
            onClick={() => refresh.mutate(text)}
          >
            Leer texto
          </Button>
        </div>
      ) : null}
      {result && !blocked && !result.draft.message && result.changes.length === 0 ? (
        <p className="text-sm text-muted-foreground">La publicación dice lo mismo que acá.</p>
      ) : null}
      {result && result.changes.length > 0 ? (
        <ul aria-label="Cambios en la publicación" className="flex flex-col gap-2">
          {result.changes.map((change) => {
            const done = applied.includes(change.field);
            return (
              <li
                key={change.field}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm"
              >
                <span className="min-w-0 break-words">
                  <span className="font-medium">{fieldLabels[change.field] ?? change.field}:</span>{" "}
                  <span className="text-muted-foreground line-through">
                    {changeValue(change, change.current)}
                  </span>{" "}
                  → {changeValue(change, change.read)}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={done}
                  aria-label={`Aplicar ${fieldLabels[change.field] ?? change.field}`}
                  onClick={() => {
                    onApply(change);
                    setApplied((current) => [...current, change.field]);
                  }}
                >
                  {done ? "Aplicado" : "Aplicar"}
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {applied.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Lo aplicado queda en el formulario: tocá «Guardar» para que quede.
        </p>
      ) : null}
    </section>
  );
}
