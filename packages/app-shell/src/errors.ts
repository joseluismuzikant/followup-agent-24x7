import { ApiRequestError } from "./api";

/** Codes every product's API can answer, in Spanish. Each panel adds its own. */
export const baseErrorMessages: Record<string, string> = {
  internal_error: "Ocurrió un error inesperado. Probá de nuevo.",
  database_unavailable: "El servicio no está disponible. Probá en unos minutos.",
  forbidden: "No tenés permisos para hacer este cambio.",
  not_found: "No encontramos lo que buscabas.",
  validation_error: "Revisá los datos ingresados.",
  profile_not_found: "Tu cuenta todavía no tiene un negocio. Completá el alta.",
  tenant_suspended: "Tu cuenta está suspendida.",
  tenant_not_found: "No encontramos ese negocio.",
  business_type_invalid: "Elegí un tipo de negocio válido.",
  tenant_name_invalid: "El nombre del negocio no es válido.",
  tenant_slug_invalid: "El nombre del negocio no es válido.",
  tenant_slug_taken: "Ya existe un negocio con ese nombre.",
  team_hours_invalid: "Revisá los horarios: cada día necesita un horario de apertura anterior al de cierre.",
  notification_email_invalid:
    "Revisá los emails de aviso: ingresá entre 1 y 5 direcciones válidas.",
  onboarding_step_invalid: "Ese paso todavía no está disponible.",
  import_file_invalid: "No pudimos leer el archivo. Subí un CSV o Excel con las columnas de la plantilla.",
  import_not_found: "Ese informe de importación ya no está disponible.",
  invalid_credentials: "El email o la clave no son correctos.",
  password_too_short: "La clave tiene que tener al menos 8 caracteres.",
  password_too_long: "La clave puede tener hasta 72 caracteres.",
  password_is_email: "La clave no puede ser tu email.",
  password_change_required: "Antes de seguir, elegí tu propia clave.",
  not_invited: "Tu email todavía no está habilitado. Pedile acceso a un administrador.",
  invitation_not_found: "Ese link de invitación no es válido.",
  invitation_expired: "Ese link venció. Pedile al administrador que te lo reenvíe.",
  invitation_used: "Ese link ya se usó. Entrá con tu email y tu clave.",
  owner_email_taken: "Ese email ya tiene un negocio en este producto.",
  owner_already_joined: "El dueño ya entró y eligió su clave.",
  account_conflict: "Ese email ya existe en el proveedor de acceso. Escribinos a soporte.",
  auth_provider_unavailable: "El servicio de acceso no responde. Probá en unos minutos.",
};

/** Unexpected failures (a 5xx, or a code without a message) carry the request's
 * "Código de referencia", so a customer can report it and we can find it in the logs. */
export function withReference(
  message: string | undefined,
  error: ApiRequestError,
  fallback: string,
): string {
  const unexpected = error.status >= 500 || message === undefined;
  const text = message ?? fallback;
  return unexpected && error.reference ? `${text} Código de referencia: ${error.reference}.` : text;
}

/** A panel's `apiErrorMessage`, from its messages (on top of the base ones). */
export function errorMessages(messages: Record<string, string>) {
  const all = { ...baseErrorMessages, ...messages };
  return (error: unknown, fallback: string): string =>
    error instanceof ApiRequestError ? withReference(all[error.code], error, fallback) : fallback;
}
