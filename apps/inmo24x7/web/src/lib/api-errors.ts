import { ApiRequestError } from "@followup/api-client-inmo24x7";

const messages: Record<string, string> = {
  database_unavailable: "El servicio no está disponible. Probá en unos minutos.",
  internal_error: "Ocurrió un error inesperado. Probá de nuevo.",
  not_found: "No encontramos lo que buscabas.",
  validation_error: "Revisá los datos ingresados.",
};

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    return messages[error.code] ?? fallback;
  }
  return fallback;
}
