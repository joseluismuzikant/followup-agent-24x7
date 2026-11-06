import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppErrorBoundary, initSentry } from "@followup/observability";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { AuthProvider } from "./lib/auth";
import { router } from "./router";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

// Errors to Sentry when VITE_SENTRY_DSN was set at build time (off otherwise).
initSentry({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  release: import.meta.env.VITE_RELEASE,
  environment: import.meta.env.VITE_SENTRY_ENVIRONMENT,
  area: "backoffice",
});

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element not found");
}

createRoot(root).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>,
);
