import type { Guarantee, PropertyConditions } from "@followup/api-client-inmo24x7";
import { cn, FormField, Input, SegmentedControl } from "@followup/ui";
import { useId } from "react";

import {
  FLAG_LABELS,
  type FlagField,
  GUARANTEES,
  type Operation,
  RENT_FLAGS,
  SALE_FLAGS,
  yesNo,
} from "../../lib/conditions";

type Tri = "yes" | "no" | "unknown";

const TRI_OPTIONS = [
  { value: "yes", label: "Sí" },
  { value: "no", label: "No" },
  { value: "unknown", label: "No informado" },
] as const;

function toTri(value: boolean | null | undefined): Tri {
  return value === true ? "yes" : value === false ? "no" : "unknown";
}

function fromTri(value: Tri): boolean | null {
  return value === "yes" ? true : value === "no" ? false : null;
}

export interface ConditionsFieldsProps {
  operation: Operation;
  value: PropertyConditions;
  onChange: (value: PropertyConditions) => void;
  /** The agency's defaults for this operation: shown where the property says nothing. */
  defaults?: PropertyConditions;
  /** "Condiciones generales" edits the defaults themselves (no free text). */
  showText?: boolean;
  error?: string;
}

/** Requirements and features of a property (or the agency's defaults), only those of the
 * operation, each Sí / No / No informado. */
export function ConditionsFields({
  operation,
  value,
  onChange,
  defaults,
  showText = true,
  error,
}: ConditionsFieldsProps) {
  const ids = { months: useId(), text: useId() };
  const flags = operation === "rent" ? RENT_FLAGS : SALE_FLAGS;
  const set = (changes: Partial<PropertyConditions>) => onChange({ ...value, ...changes });

  function fromDefault(field: keyof PropertyConditions, label: string): string | undefined {
    const own = value[field];
    const fallback = defaults?.[field];
    if ((own === null || own === undefined) && fallback !== null && fallback !== undefined) {
      return `Por defecto: ${label} (Condiciones generales).`;
    }
    return undefined;
  }

  function toggle(guarantee: Guarantee) {
    const current = value.garantias ?? [];
    const next = current.includes(guarantee)
      ? current.filter((item) => item !== guarantee)
      : [...current, guarantee];
    set({ garantias: next.length ? next : null });
  }

  return (
    <div className="flex flex-col gap-4">
      {operation === "rent" ? (
        <>
          <FormField
            label="Garantías que acepta"
            hint={fromDefault(
              "garantias",
              (defaults?.garantias ?? [])
                .map((item) => GUARANTEES.find((g) => g.value === item)?.label)
                .join(", "),
            )}
          >
            <div className="flex flex-wrap gap-2" role="group" aria-label="Garantías que acepta">
              {GUARANTEES.map((guarantee) => {
                const on = (value.garantias ?? []).includes(guarantee.value);
                return (
                  <button
                    key={guarantee.value}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggle(guarantee.value)}
                    className={cn(
                      "min-h-11 rounded-full border px-3 py-1 text-sm transition-colors md:min-h-0",
                      on ? "border-primary bg-primary text-primary-foreground" : "bg-card",
                    )}
                  >
                    {guarantee.label}
                  </button>
                );
              })}
            </div>
          </FormField>
          <FormField
            label="Contrato mínimo (meses)"
            htmlFor={ids.months}
            hint={fromDefault("contrato_minimo_meses", `${defaults?.contrato_minimo_meses} meses`)}
            error={error}
          >
            <Input
              id={ids.months}
              inputMode="numeric"
              className="w-32"
              value={value.contrato_minimo_meses ?? ""}
              placeholder="24"
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                set({ contrato_minimo_meses: digits ? Number(digits) : null });
              }}
            />
          </FormField>
        </>
      ) : null}
      {flags.map((flag: FlagField) => (
        <FormField key={flag} label={FLAG_LABELS[flag]} hint={fromDefault(flag, yesNo(defaults?.[flag]))}>
          <SegmentedControl
            ariaLabel={FLAG_LABELS[flag]}
            options={TRI_OPTIONS}
            value={toTri(value[flag])}
            className="flex-wrap"
            onChange={(next) => set({ [flag]: fromTri(next) })}
          />
        </FormField>
      ))}
      {showText ? (
        <FormField
          label="Otras condiciones"
          htmlFor={ids.text}
          hint="Texto libre que Sofía puede mencionar (por ejemplo «requiere dos garantías»). No se usa para comparar."
        >
          <textarea
            id={ids.text}
            maxLength={300}
            rows={2}
            value={value.condiciones ?? ""}
            onChange={(event) => set({ condiciones: event.target.value || null })}
            className="rounded-md border bg-card p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </FormField>
      ) : null}
    </div>
  );
}
