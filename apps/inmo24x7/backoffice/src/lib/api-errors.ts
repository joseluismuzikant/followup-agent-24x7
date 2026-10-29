import { ApiRequestError } from "@followup/api-client-inmo24x7";

const messages: Record<string, string> = {
  admin_required: "Necesitás permisos de administrador.",
  agent_unavailable: "El agente no pudo responder ahora. Probá de nuevo.",
  database_unavailable: "La base de datos no está disponible. Probá en unos minutos.",
  internal_error: "Ocurrió un error inesperado. Probá de nuevo.",
  not_found: "No encontramos lo que buscabas.",
  simulator_limit_reached:
    "Este negocio llegó al límite de mensajes de prueba de hoy. Mañana se puede seguir probando.",
  tenant_not_found: "No encontramos ese negocio.",
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
