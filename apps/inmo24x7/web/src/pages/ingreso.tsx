import { SignIn } from "@followup/app-shell";

import { account } from "../api/client";
import { authMode } from "../lib/auth-mode";
import { getSupabase } from "../lib/supabase";

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
      showLegal
    />
  );
}
