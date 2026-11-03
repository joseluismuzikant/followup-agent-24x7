import { Navigate, useParams } from "react-router";

/** The Day 5 manual connection page now lives in the business detail (S9). */
export function WhatsAppPage() {
  const { tenantId = "" } = useParams();
  return <Navigate to={`/negocios/${tenantId}`} replace />;
}
