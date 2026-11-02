import type { PropertyInput } from "@followup/api-client-inmo24x7";

const thousands = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

/** "USD 185.000" or "$ 850.000". */
export function formatPrice(price: number, currency: "ARS" | "USD"): string {
  return `${currency === "USD" ? "USD" : "$"} ${thousands.format(price)}`;
}

export const operationLabels = { sale: "Venta", rent: "Alquiler" } as const;

export interface PropertyDraft {
  title: string;
  address: string;
  operation: "sale" | "rent";
  zone: string;
  price: string;
  currency: "ARS" | "USD";
  rooms: string;
  link: string;
  /** Kept as it is: publishing and pausing happen from the list. */
  status: "published" | "paused";
}

export type PropertyDraftErrors = Partial<Record<keyof PropertyDraft, string>>;

/** Digits only, so "850.000" and "850000" are the same price. */
export function parsePrice(text: string): number | null {
  const digits = text.replace(/[.\s$]|USD/gi, "");
  return /^\d+$/.test(digits) && Number(digits) > 0 ? Number(digits) : null;
}

export function isWebLink(text: string): boolean {
  try {
    const url = new URL(text.trim());
    return (url.protocol === "http:" || url.protocol === "https:") && /\.[a-z]{2,}$/i.test(url.hostname);
  } catch {
    return false;
  }
}

/** The same rules the API applies, so the form explains each problem in place. */
export function validateProperty(draft: PropertyDraft): {
  errors: PropertyDraftErrors;
  input: PropertyInput | null;
} {
  const errors: PropertyDraftErrors = {};
  if (!draft.title.trim()) errors.title = "Falta el título.";
  if (!draft.address.trim()) errors.address = "Falta la dirección.";
  if (!draft.zone.trim()) errors.zone = "Falta la zona.";
  const price = parsePrice(draft.price);
  if (price === null) errors.price = "Ingresá un precio mayor a cero.";
  const rooms = Number(draft.rooms);
  if (!Number.isInteger(rooms) || rooms < 1 || rooms > 20) {
    errors.rooms = "Los ambientes tienen que ser un número entre 1 y 20.";
  }
  if (!draft.link.trim()) errors.link = "Falta el link del aviso.";
  else if (!isWebLink(draft.link)) errors.link = "El link no es una dirección web válida.";
  if (Object.keys(errors).length > 0 || price === null) {
    return { errors, input: null };
  }
  return {
    errors,
    input: {
      title: draft.title.trim(),
      address: draft.address.trim(),
      operation: draft.operation,
      zone: draft.zone.trim(),
      price,
      currency: draft.currency,
      rooms,
      link: draft.link.trim(),
      status: draft.status,
    },
  };
}
