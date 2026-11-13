import { ChangePasswordPage, InvitationPage, RequireAccount } from "@followup/app-shell";
import { createBrowserRouter, Navigate } from "react-router";

import { account } from "./api/client";

import { AppShell } from "./components/AppShell";
import { RequireProfile } from "./components/RequireProfile";
import { ResumeOnboarding } from "./components/ResumeOnboarding";
import { RedirectIfAuthed, RequireAuth, useAuth } from "./lib/auth";
import { authMode } from "./lib/auth-mode";
import { PRODUCT_NAME } from "./lib/product";
import { getSupabase } from "./lib/supabase";
import { ClientePage } from "./pages/cliente";
import { ClientesPage } from "./pages/clientes";
import { ConfiguracionPage } from "./pages/configuracion";
import { FacturasPage } from "./pages/facturas";
import { IngresoPage } from "./pages/ingreso";
import { InicioPage } from "./pages/inicio";
import { OnboardingPage } from "./pages/onboarding";
import { PagoPage } from "./pages/pago";
import { RecordatoriosPage } from "./pages/recordatorios";

const accountPage = { productName: PRODUCT_NAME, account, authMode, getSupabase, useAuth };

export const router = createBrowserRouter([
  {
    path: "/ingreso",
    element: (
      <RedirectIfAuthed>
        <IngresoPage />
      </RedirectIfAuthed>
    ),
  },
  { path: "/invitacion", element: <InvitationPage {...accountPage} /> },
  { path: "/cambiar-clave", element: <ChangePasswordPage {...accountPage} /> },
  // A reminder's "Ver y pagar": public, no login.
  { path: "/p/:token", element: <PagoPage /> },
  {
    path: "/onboarding/:step?",
    element: (
      <RequireAuth>
        <RequireAccount account={account}>
          <OnboardingPage />
        </RequireAccount>
      </RequireAuth>
    ),
  },
  {
    element: (
      <RequireAuth>
        <RequireAccount account={account}>
          <RequireProfile>
            <ResumeOnboarding>
              <AppShell />
            </ResumeOnboarding>
          </RequireProfile>
        </RequireAccount>
      </RequireAuth>
    ),
    children: [
      { path: "/", element: <InicioPage /> },
      { path: "/facturas", element: <FacturasPage /> },
      { path: "/clientes", element: <ClientesPage /> },
      { path: "/clientes/:id", element: <ClientePage /> },
      { path: "/recordatorios", element: <RecordatoriosPage /> },
      { path: "/configuracion", element: <ConfiguracionPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
