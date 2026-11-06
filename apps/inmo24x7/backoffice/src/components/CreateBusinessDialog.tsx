import { CreateBusinessDialog as ShellCreateBusinessDialog } from "@followup/app-shell";
import { useNavigate } from "react-router";

import { createBusiness } from "../api/backoffice";

/** "Dar de alta un negocio": the business, its owner's account and the invitation email. */
export function CreateBusinessDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <ShellCreateBusinessDialog
      open={open}
      onClose={onClose}
      businessType="inmobiliaria"
      create={createBusiness}
      onCreated={(business) => void navigate(`/negocios/${business.id}`)}
    />
  );
}
