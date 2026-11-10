import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppErrorBoundary, initSentry } from "@followup/observability";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterLinkProvider } from "@followup/app-shell";
import { RouterProvider } from "react-router";

import { AuthProvider } from "./lib/auth";
import { router } from "./router";
import "./styles.css";

const queryClient: QueryClient = new QueryClient({
  // A business suspended while someone is using the panel: /me shows the suspended screen.
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (
        error instanceof ApiRequestError &&
        error.code === "tenant_suspended" &&
        query.queryKey[0] !== "me"
      ) {
        void queryClient.invalidateQueries({ queryKey: ["me"] });
      }
    },
  }),
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
  area: "panel",
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
          <RouterLinkProvider>
            <RouterProvider router={router} />
          </RouterLinkProvider>
        </AuthProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>,
);
