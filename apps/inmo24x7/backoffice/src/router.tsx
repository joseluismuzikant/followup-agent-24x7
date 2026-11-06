import { ChangePasswordPage } from "@followup/app-shell";
import { createBrowserRouter, Navigate } from "react-router";

import { App } from "./App";
import { account } from "./api/client";
import { useAuth } from "./lib/auth";
import { authMode } from "./lib/auth-mode";
import { getSupabase } from "./lib/supabase";
import { ConsumoPage } from "./pages/consumo";
import { ErroresPage } from "./pages/errores";
import { NegocioPage } from "./pages/negocio";
import { PlanesPage } from "./pages/planes";
import { SimuladorPage } from "./pages/simulador";
import { SistemaPage } from "./pages/sistema";
import { WhatsAppPage } from "./pages/whatsapp";

export const router = createBrowserRouter([
  { path: "/", element: <App /> },
  // "¿Olvidaste tu clave?" comes back here with Supabase's recovery session.
  {
    path: "/cambiar-clave",
    element: (
      <ChangePasswordPage
        productName="inmo24x7"
        areaName="Backoffice"
        account={account}
        authMode={authMode}
        getSupabase={getSupabase}
        useAuth={useAuth}
      />
    ),
  },
  { path: "/negocios/:tenantId", element: <NegocioPage /> },
  { path: "/negocios/:tenantId/whatsapp", element: <WhatsAppPage /> },
  { path: "/simulador", element: <SimuladorPage /> },
  { path: "/sistema", element: <SistemaPage /> },
  { path: "/errores", element: <ErroresPage /> },
  { path: "/consumo", element: <ConsumoPage /> },
  { path: "/planes", element: <PlanesPage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
