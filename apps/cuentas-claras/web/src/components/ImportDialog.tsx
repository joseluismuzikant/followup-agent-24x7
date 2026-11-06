import { Dialog } from "@followup/ui";

import { ImportPanel } from "./ImportPanel";

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ImportDialog({ open, onClose }: ImportDialogProps) {
  return (
    <Dialog open={open} title="Importar facturas" onClose={onClose}>
      {/* Remounted on each open: a new file starts with a clean report. */}
      {open ? <ImportPanel /> : null}
    </Dialog>
  );
}
