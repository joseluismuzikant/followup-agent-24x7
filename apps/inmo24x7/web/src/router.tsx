import { ChangePasswordPage, InvitationPage, RequireAccount } from "@followup/app-shell";
import { createBrowserRouter, Navigate } from "react-router";

import { account } from "./api/client";

import { AppShell } from "./components/AppShell";
import { RequireProfile } from "./components/RequireProfile";
import { ResumeOnboarding } from "./components/ResumeOnboarding";
import { RedirectIfAuthed, RequireAuth, useAuth } from "./lib/auth";
import { authMode } from "./lib/auth-mode";
import { getSupabase } from "./lib/supabase";
import { AgentePage } from "./pages/agente";
import { ConfiguracionPage } from "./pages/configuracion";
import { ConsultasPage } from "./pages/consultas";
import { EjemploPage } from "./pages/ejemplo";
import { IngresoPage } from "./pages/ingreso";
import { InicioPage } from "./pages/inicio";
import { OnboardingPage } from "./pages/onboarding";
import { ProbarPage } from "./pages/probar";
import { PropiedadesPage } from "./pages/propiedades";

const accountPage = { productName: "inmo24x7", account, authMode, getSupabase, useAuth };

export const router = createBrowserRouter([
  {
    path: "/ingreso",
    element: (
      <RedirectIfAuthed>
        <IngresoPage />
      </RedirectIfAuthed>
    ),
  },
  { path: "/ejemplo/:id", element: <EjemploPage /> },
  { path: "/invitacion", element: <InvitationPage {...accountPage} /> },
  { path: "/cambiar-clave", element: <ChangePasswordPage {...accountPage} /> },
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
      { path: "/consultas", element: <ConsultasPage /> },
      { path: "/propiedades", element: <PropiedadesPage /> },
      { path: "/agente", element: <AgentePage /> },
      { path: "/probar", element: <ProbarPage /> },
      { path: "/configuracion", element: <ConfiguracionPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
