import type {
  ConditionStatus,
  Guarantee,
  PropertyConditions,
} from "@followup/api-client-inmo24x7";

export type Operation = "rent" | "sale";
export type FlagField =
  | "temporal"
  | "amueblado"
  | "mascotas"
  | "apto_profesional"
  | "apto_credito"
  | "acepta_financiacion"
  | "acepta_permuta";

/** The conditions of each operation, in the order the form shows them. */
export const RENT_FLAGS: FlagField[] = ["temporal", "amueblado", "mascotas", "apto_profesional"];
export const SALE_FLAGS: FlagField[] = [
  "apto_credito",
  "acepta_financiacion",
  "acepta_permuta",
  "mascotas",
  "apto_profesional",
];

export const FLAG_LABELS: Record<FlagField, string> = {
  temporal: "Acepta alquiler temporario",
  amueblado: "Amueblada",
  mascotas: "Acepta mascotas",
  apto_profesional: "Apta uso profesional",
  apto_credito: "Apta crédito hipotecario",
  acepta_financiacion: "Acepta financiación",
  acepta_permuta: "Acepta permuta",
};

export const GUARANTEES: { value: Guarantee; label: string }[] = [
  { value: "caucion", label: "Seguro de caución" },
  { value: "propietaria", label: "Garantía propietaria" },
  { value: "recibo_de_sueldo", label: "Recibo de sueldo" },
  { value: "otra", label: "Otra" },
];

export const EMPTY_CONDITIONS: PropertyConditions = {
  garantias: null,
  contrato_minimo_meses: null,
  temporal: null,
  amueblado: null,
  mascotas: null,
  apto_profesional: null,
  apto_credito: null,
  acepta_financiacion: null,
  acepta_permuta: null,
  condiciones: null,
};

/** Only the fields of the operation (the others are sent empty). */
export function forOperation(conditions: PropertyConditions, operation: Operation): PropertyConditions {
  const flags = operation === "rent" ? RENT_FLAGS : SALE_FLAGS;
  const kept: PropertyConditions = { ...EMPTY_CONDITIONS, condiciones: conditions.condiciones ?? null };
  for (const flag of flags) {
    kept[flag] = conditions[flag] ?? null;
  }
  if (operation === "rent") {
    kept.garantias = conditions.garantias?.length ? conditions.garantias : null;
    kept.contrato_minimo_meses = conditions.contrato_minimo_meses ?? null;
  }
  return kept;
}

export function yesNo(value: boolean | null | undefined): string {
  return value === true ? "Sí" : value === false ? "No" : "No informado";
}

const SHORT_GUARANTEES: Record<Guarantee, string> = {
  caucion: "Caución",
  propietaria: "Propietaria",
  recibo_de_sueldo: "Recibo",
  otra: "Otra garantía",
};

/** The few conditions worth a badge in the list ("Caución", "Mascotas", "Apto crédito"). */
export function conditionBadges(conditions: PropertyConditions, max = 3): string[] {
  const badges: string[] = [];
  for (const guarantee of conditions.garantias ?? []) {
    badges.push(SHORT_GUARANTEES[guarantee]);
  }
  if (conditions.contrato_minimo_meses) {
    badges.push(`Mín. ${conditions.contrato_minimo_meses} meses`);
  }
  if (conditions.mascotas === true) {
    badges.push("Mascotas");
  } else if (conditions.mascotas === false) {
    badges.push("Sin mascotas");
  }
  if (conditions.apto_credito) {
    badges.push("Apto crédito");
  }
  if (conditions.temporal) {
    badges.push("Temporario");
  }
  if (conditions.amueblado) {
    badges.push("Amueblada");
  }
  return badges.slice(0, max);
}

export const STATUS_LABELS: Record<ConditionStatus, string> = {
  cumple: "Cumple",
  no_cumple: "No cumple",
  sin_datos: "Sin datos",
};

export const STATUS_TONES: Record<ConditionStatus, "success" | "danger" | "neutral"> = {
  cumple: "success",
  no_cumple: "danger",
  sin_datos: "neutral",
};
