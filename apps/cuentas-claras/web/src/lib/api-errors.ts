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
});
