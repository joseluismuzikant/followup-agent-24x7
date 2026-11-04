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
  whatsapp_api_error: "Meta rechazó el pedido.",
  whatsapp_connection_invalid:
    "Revisá los datos: el phone_number_id y el WABA id son identificadores sin espacios, y una conexión nueva necesita el token.",
  whatsapp_not_connected: "Este negocio todavía no tiene un número conectado.",
  whatsapp_phone_number_taken: "Ese número ya está conectado a otro negocio.",
  tenant_name_invalid: "El nombre del negocio no es válido.",
  tenant_slug_invalid: "El nombre del negocio no es válido.",
  tenant_slug_taken: "Ya existe un negocio con ese nombre.",
  validation_error: "Revisá los datos ingresados.",
  owner_email_taken: "Ese email ya tiene una cuenta o ya tiene un negocio esperándolo.",
  business_type_invalid: "Elegí un tipo de negocio válido.",
  suspension_reason_invalid: "Escribí el motivo de la suspensión (hasta 500 caracteres).",
  whatsapp_signup_restart:
    "No hay una conexión con Meta a medio terminar para reintentar: el cliente tiene que volver a conectar.",
  whatsapp_signup_failed: "Meta rechazó un paso de la configuración.",
  tenant_has_no_owner: "Este negocio todavía no tiene dueño a quien mandarle el link.",
};

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    const message = messages[error.code] ?? fallback;
    const metaCode = "metaCode" in error ? error.metaCode : null;
    return metaCode ? `${message} Código de Meta: ${metaCode}.` : message;
  }
  return fallback;
}
