import type { IntegrationDelivery } from "@followup/api-client-inmo24x7";

export const deliveryStatusLabels: Record<IntegrationDelivery["status"], string> = {
  pending: "En cola",
  retrying: "Reintentando",
  delivered: "Enviado",
  failed: "Error",
};

export const deliveryStatusTones: Record<
  IntegrationDelivery["status"],
  "neutral" | "warning" | "success" | "danger"
> = {
  pending: "neutral",
  retrying: "warning",
  delivered: "success",
  failed: "danger",
};

const errorLabels: Record<string, string> = {
  tokko_key_invalid: "Tokko rechazó la clave",
  tokko_unavailable: "Tokko no respondió",
  tokko_bad_response: "Respuesta inesperada de Tokko",
  tokko_contact_rejected: "Tokko rechazó el contacto",
  webhook_unreachable: "No pudimos conectar con la dirección",
  webhook_rejected: "El webhook respondió con error",
  webhook_server_error: "El webhook respondió con error del servidor",
  integration_disabled: "La integración estaba desactivada",
  lead_not_found: "La consulta ya no existe",
};

export function integrationErrorLabel(code: string | null | undefined): string {
  if (!code) {
    return "";
  }
  return errorLabels[code] ?? "Error al enviar";
}

/** "Enviado a Tokko ✓" / "Error al enviar a Tokko: …" for the lead panel. */
export function deliveryLine(item: IntegrationDelivery): string {
  const target = item.provider === "tokko" ? "Tokko" : "tu webhook";
  switch (item.status) {
    case "delivered":
      return `Enviado a ${target} ✓`;
    case "retrying":
      return `Reintentando el envío a ${target}`;
    case "pending":
      return `Enviando a ${target}…`;
    default:
      return `Error al enviar a ${target}: ${integrationErrorLabel(item.error_code)}`;
  }
}

/** The one line an agency pastes on its website. */
export function widgetSnippet(origin: string, publicId: string): string {
  return `<script src="${origin}/widget.js" data-agencia="${publicId}" async></script>`;
}

/** The text the button writes on a property page (the same as widget.js). */
export function widgetMessage(title: string, code: string): string {
  return `Hola, me interesa la propiedad «${title}» (ref. ${code})`;
}

export const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
