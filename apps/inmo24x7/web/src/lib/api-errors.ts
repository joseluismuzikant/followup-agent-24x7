import { ApiRequestError } from "@followup/api-client-inmo24x7";

const messages: Record<string, string> = {
  agent_unavailable: "Tu agente no pudo responder ahora. Probá de nuevo.",
  agent_setup_conflict: "Alguien más guardó cambios. Recargá para ver la última versión.",
  agent_name_invalid: "El nombre del agente debe tener entre 1 y 40 caracteres.",
  business_type_invalid: "Elegí un tipo de negocio válido.",
  database_unavailable: "El servicio no está disponible. Probá en unos minutos.",
  internal_error: "Ocurrió un error inesperado. Probá de nuevo.",
  forbidden: "No tenés permisos para hacer este cambio.",
  import_file_invalid:
    "No pudimos leer el archivo. Subí un CSV o Excel con las columnas de la plantilla.",
  import_not_found: "Ese informe de importación ya no está disponible.",
  import_too_large: "El archivo es muy grande: hasta 5 MB y 2.000 propiedades por vez.",
  lead_not_found: "No encontramos esa consulta.",
  not_found: "No encontramos lo que buscabas.",
  notification_email_invalid: "Revisá los emails de aviso: ingresá entre 1 y 5 direcciones válidas.",
  onboarding_step_invalid: "Ese paso todavía no está disponible.",
  profile_not_found: "Tu cuenta todavía no tiene un negocio. Completá el alta.",
  property_invalid: "Revisá los datos de la propiedad.",
  property_link_taken: "Ya tenés otra propiedad con ese link.",
  property_not_found: "No encontramos esa propiedad.",
  questions_invalid:
    "Revisá las preguntas: cada una necesita un texto, y podés tener hasta 10.",
  simulator_limit_reached:
    "Llegaste al límite de mensajes de prueba de hoy. Mañana podés seguir probando.",
  setup_not_found: "Todavía no encontramos la configuración de tu negocio.",
  team_hours_invalid: "Revisá el horario del equipo.",
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
