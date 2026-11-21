import { type LegalLinks, SignIn } from "@followup/app-shell";

import { account } from "../api/client";
import { authMode } from "../lib/auth-mode";
import { getSupabase } from "../lib/supabase";

/** The legal pages on the landing (www.inmo24x7.com). */
export const LEGAL_LINKS: LegalLinks = {
  termsUrl: "https://www.inmo24x7.com/terminos",
  privacyUrl: "https://www.inmo24x7.com/privacidad",
};

export function IngresoPage() {
  return (
    <SignIn
      productName="inmo24x7"
      title="Entrá a tu panel"
      description="Tu agente de WhatsApp que responde, califica y agenda visitas las 24 horas."
      authMode={authMode}
      getSupabase={getSupabase}
      account={account}
      devPlaceholder="dueno@inmobiliariasur.test"
      legalLinks={LEGAL_LINKS}
    />
  );
}
