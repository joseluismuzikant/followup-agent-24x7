import type { ImportReport } from "@followup/api-client-cuentas-claras";
import { Button, FileDropzone } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { downloadImportErrors, downloadImportTemplate, importInvoices } from "../api/invoices";
import { apiErrorMessage } from "../lib/api-errors";

const SHOWN_ERRORS = 10;

interface ImportPanelProps {
  onImported?: (report: ImportReport) => void;
}

/** "Importar facturas": the template, the dropzone and the report (wizard and Facturas). */
export function ImportPanel({ onImported }: ImportPanelProps) {
  const queryClient = useQueryClient();
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: importInvoices,
    onSuccess: async (report) => {
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      await queryClient.invalidateQueries({ queryKey: ["clients"] });
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      onImported?.(report);
    },
  });

  async function download(action: () => Promise<void>) {
    setDownloadError(null);
    try {
      await action();
    } catch (failure) {
      setDownloadError(apiErrorMessage(failure, "No pudimos descargar el archivo."));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <FileDropzone
        accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        label={upload.isPending ? "Importando..." : "Arrastrá tu archivo o hacé clic para elegirlo"}
        hint="CSV o Excel (.xlsx) exportado de tu sistema de facturación, hasta 5 MB y 5.000 facturas."
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
  );
}

export function ImportReportCard({
  report,
  onDownloadErrors,
}: {
  report: ImportReport;
  onDownloadErrors: () => void;
}) {
  const imported = report.created + report.updated;
  const hidden = report.errors.length - SHOWN_ERRORS;

  return (
    <section
      aria-label="Resultado de la importación"
      className="flex flex-col gap-2 rounded-md border bg-muted/40 p-3"
    >
      <p className="font-semibold">
        Importamos {imported} de {report.total}
      </p>
      <p className="text-sm text-muted-foreground">
        {report.created} nuevas · {report.updated} actualizadas
        {report.skipped > 0 ? ` · ${report.skipped} sin cambios` : ""}
      </p>
      {report.warnings.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm text-amber-800">
          {report.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {report.failed > 0 ? (
        <>
          <ul className="flex flex-col gap-1 text-sm text-destructive">
            {report.errors.slice(0, SHOWN_ERRORS).map((error) => (
              <li key={error.row}>{error.error}</li>
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
