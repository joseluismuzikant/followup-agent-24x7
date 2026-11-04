import { ErrorBoundary } from "@sentry/react";
import { Button } from "@followup/ui";
import type { ReactNode } from "react";

export function ErrorFallback() {
  return (
    <div role="alert" className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="flex max-w-sm flex-col items-center gap-4 text-center">
        <h1 className="text-lg font-semibold">Algo salió mal. Ya nos llegó el aviso.</h1>
        <p className="text-sm text-muted-foreground">
          Recargá la página para seguir. Si vuelve a pasar, escribinos.
        </p>
        <Button onClick={() => window.location.reload()}>Recargar</Button>
      </div>
    </div>
  );
}

/** Catches render errors anywhere in the app (reported to Sentry when it is on). */
export function AppErrorBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary fallback={<ErrorFallback />}>{children}</ErrorBoundary>;
}
