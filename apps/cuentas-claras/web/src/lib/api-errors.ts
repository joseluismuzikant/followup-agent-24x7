import { errorMessages } from "@followup/app-shell";

export const apiErrorMessage = errorMessages({
  client_not_found: "No encontramos ese cliente.",
  client_invalid: "Revisá los datos del cliente.",
  cuit_invalid: "El CUIT no es válido: son 11 números y el último es el dígito verificador.",
  cuit_taken: "Ya tenés otro cliente con ese CUIT.",
  invoice_not_found: "No encontramos esa factura.",
  invoice_invalid: "Revisá los datos de la factura.",
  invoice_number_taken: "Ya tenés una factura con ese tipo, punto de venta y número.",
  invoice_already_paid: "Esa factura ya figura pagada.",
  import_too_large: "El archivo es muy grande: hasta 5 MB y 5.000 facturas por vez.",
  tenant_suspended: "Tu cuenta está suspendida.",
  reminder_policy_invalid: "Revisá los pasos: cada uno en un día distinto, entre 30 días antes y 90 después, y el aviso al dueño al final.",
  template_invalid:
    "Revisá el texto: cada dato una sola vez, nunca al principio ni al final, ni dos seguidos.",
  transfer_details_invalid: "Revisá los datos: el CBU o CVU tiene 22 números, el alias entre 6 y 20 letras, números o puntos.",
  payment_link_not_found: "Este link no existe o venció. Pedile uno nuevo a quien te lo mandó.",
  whatsapp_connection_invalid: "Los datos que mandó Meta no son válidos. Volvé a conectar.",
  whatsapp_phone_number_taken:
    "Ese número ya está conectado a otra cuenta de Cuentas Claras. Elegí otro número o escribinos.",
  whatsapp_signup_restart:
    "La conexión con Meta se cortó antes de terminar. Tocá “Conectar WhatsApp” de nuevo.",
});
