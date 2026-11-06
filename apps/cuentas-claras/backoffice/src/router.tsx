import { ChangePasswordPage } from "@followup/app-shell";
import { createBrowserRouter, Navigate } from "react-router";

import { App } from "./App";
import { account } from "./api/client";
import { useAuth } from "./lib/auth";
import { authMode } from "./lib/auth-mode";
import { PRODUCT_NAME } from "./lib/labels";
import { getSupabase } from "./lib/supabase";
import { NegocioPage } from "./pages/negocio";

export const router = createBrowserRouter([
  { path: "/", element: <App /> },
  { path: "/negocios/:tenantId", element: <NegocioPage /> },
  // "¿Olvidaste tu clave?" comes back here with Supabase's recovery session.
  {
    path: "/cambiar-clave",
    element: (
      <ChangePasswordPage
        productName={PRODUCT_NAME}
        areaName="Backoffice"
        account={account}
        authMode={authMode}
        getSupabase={getSupabase}
        useAuth={useAuth}
      />
    ),
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
