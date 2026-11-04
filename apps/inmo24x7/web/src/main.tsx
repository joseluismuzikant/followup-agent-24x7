import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
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

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element not found");
}

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
