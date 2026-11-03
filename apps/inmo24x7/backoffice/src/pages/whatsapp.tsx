import { PanelLayout } from "@followup/ui";
import { useLocation, useParams } from "react-router";

import { RequireAdmin } from "../components/RequireAdmin";
import { WhatsAppConnectionPanel } from "../components/WhatsAppConnection";
import { navItems } from "../lib/nav";

export function WhatsAppPage() {
  const location = useLocation();
  const { tenantId = "" } = useParams();
  return (
    <RequireAdmin>
      <PanelLayout
        productName="inmo24x7"
        areaName="Backoffice"
        title="WhatsApp"
        description="Conexión manual del número del negocio (Embedded Signup llega el día 7)."
        navItems={navItems(location.pathname)}
      >
        <WhatsAppConnectionPanel tenantId={tenantId} />
      </PanelLayout>
    </RequireAdmin>
  );
}
