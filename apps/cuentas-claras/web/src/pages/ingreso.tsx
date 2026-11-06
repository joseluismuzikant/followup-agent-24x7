import { SignIn } from "@followup/app-shell";

import { account } from "../api/client";
import { authMode } from "../lib/auth-mode";
import { PRODUCT_NAME, TAGLINE } from "../lib/product";
import { getSupabase } from "../lib/supabase";

export function IngresoPage() {
  return (
    <SignIn
      productName={PRODUCT_NAME}
      title="Entrá a tu panel"
      description={
        <>
          <span className="block font-medium text-foreground">{TAGLINE}</span>
          Cargá tus facturas y te avisamos qué está vencido y qué vence esta semana. Muy pronto,
          los recordatorios salen solos por WhatsApp.
        </>
      }
      authMode={authMode}
      getSupabase={getSupabase}
      account={account}
      showLegal
      devPlaceholder="dueno@ascensoresdelta.test"
    />
  );
}
