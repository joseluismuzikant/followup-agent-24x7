import { ApiRequestError } from "@followup/api-client-inmo24x7";

const messages: Record<string, string> = {
  database_unavailable: "El servicio no está disponible. Probá en unos minutos.",
  internal_error: "Ocurrió un error inesperado. Probá de nuevo.",
  not_found: "No encontramos lo que buscabas.",
  profile_not_found: "Tu cuenta todavía no tiene un negocio. Completá el alta.",
  tenant_name_invalid: "El nombre del negocio no es válido.",
  tenant_slug_invalid: "El nombre del negocio no es válido.",
  tenant_slug_taken: "Ya existe un negocio con ese nombre.",
  validation_error: "Revisá los datos ingresados.",
};

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    return messages[error.code] ?? fallback;
  }
  return fallback;
}
