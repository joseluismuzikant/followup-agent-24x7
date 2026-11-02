import type { ImportReport } from "@followup/api-client-inmo24x7";
import { Button, Dialog, FileDropzone } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  downloadImportErrors,
  downloadImportTemplate,
  importProperties,
} from "../../api/properties";
import { apiErrorMessage } from "../../lib/api-errors";

const SHOWN_ERRORS = 10;

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
}

/** "Importar CSV o Excel": drop a file, then the S7 report. */
export function ImportDialog({ open, onClose }: ImportDialogProps) {
  const queryClient = useQueryClient();
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: importProperties,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      await queryClient.invalidateQueries({ queryKey: ["simulator"] });
    },
  });

  function close() {
    upload.reset();
    setDownloadError(null);
    onClose();
  }

  async function download(action: () => Promise<void>) {
    setDownloadError(null);
    try {
      await action();
    } catch (failure) {
      setDownloadError(apiErrorMessage(failure, "No pudimos descargar el archivo."));
    }
  }

  return (
    <Dialog open={open} title="Importar propiedades" onClose={close}>
      <div className="flex flex-col gap-4">
        <FileDropzone
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          label={upload.isPending ? "Importando..." : "Arrastrá tu archivo o hacé clic para elegirlo"}
          hint="CSV o Excel (.xlsx), hasta 5 MB y 2.000 propiedades."
          disabled={upload.isPending}
          onFile={(file) => upload.mutate(file)}
        />
        <Button
          variant="link"
          className="self-start px-0"
          onClick={() => void download(downloadImportTemplate)}
        >
          Descargar la plantilla
        </Button>

        {upload.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(upload.error, "No pudimos importar el archivo. Probá de nuevo.")}
          </p>
        ) : null}
        {upload.data ? (
          <ImportReportCard
            report={upload.data}
            onDownloadErrors={() => void download(() => downloadImportErrors(upload.data.id))}
          />
        ) : null}
        {downloadError ? (
          <p className="text-sm text-destructive" role="alert">
            {downloadError}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

export function ImportReportCard({
  report,
  onDownloadErrors,
}: {
  report: ImportReport;
  onDownloadErrors: () => void;
}) {
  const hidden = report.errors.length - SHOWN_ERRORS;
  return (
    <section
      aria-label="Resultado de la importación"
      className="flex flex-col gap-2 rounded-md border bg-muted/40 p-3"
    >
      <p className="font-semibold">
        Importamos {report.imported} de {report.total}
      </p>
      {report.failed > 0 ? (
        <>
          <ul className="flex flex-col gap-1 text-sm text-destructive">
            {report.errors.slice(0, SHOWN_ERRORS).map((error) => (
              <li key={error}>{error}</li>
            ))}
            {hidden > 0 ? <li>y {hidden} más.</li> : null}
          </ul>
          <Button variant="outline" size="sm" className="self-start" onClick={onDownloadErrors}>
            Descargar {report.failed === 1 ? "la que tiene" : `las ${report.failed} con`} errores
          </Button>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Todas las filas quedaron cargadas.</p>
      )}
    </section>
  );
}
