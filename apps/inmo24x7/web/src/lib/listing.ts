import type { ListingDraft, ListingFieldChange } from "@followup/api-client-inmo24x7";

import { formatPrice, operationLabels } from "./properties";

/** Fields the model read: the form marks them "Revisá este dato". */
export function readByModel(draft: ListingDraft | null | undefined, field: string): boolean {
  return draft?.sources[field] === "model";
}

/** Whether any of the conditions came from the model. */
export function conditionsByModel(draft: ListingDraft | null | undefined): boolean {
  if (!draft) {
    return false;
  }
  return Object.entries(draft.sources).some(
    ([field, source]) => source === "model" && field in draft.conditions,
  );
}

const thousands = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export const fieldLabels: Record<string, string> = {
  title: "Título",
  address: "Dirección",
  operation: "Operación",
  zone: "Zona",
  price: "Precio",
  currency: "Moneda",
  rooms: "Ambientes",
  status: "Estado",
};

/** A value of "Actualizar desde el link", as the panel shows it. */
export function changeValue(change: ListingFieldChange, value: string | number | null): string {
  if (value === null) {
    return "—";
  }
  switch (change.field) {
    case "operation":
      return operationLabels[value as "sale" | "rent"] ?? String(value);
    case "currency":
      return value === "USD" ? "Dólares" : "Pesos";
    case "status":
      return value === "paused" ? "Pausada" : "Publicada";
    case "price":
      return typeof value === "number" ? thousands.format(value) : value;
    default:
      return String(value);
  }
}

/** "USD 185.000", or null when the page said no price. */
export function draftPrice(draft: ListingDraft): string | null {
  return draft.price ? formatPrice(draft.price, draft.currency ?? "ARS") : null;
}
