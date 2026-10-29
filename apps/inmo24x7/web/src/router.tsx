import { createBrowserRouter, Navigate } from "react-router";

import { AppShell } from "./components/AppShell";
import { RequireProfile } from "./components/RequireProfile";
import { ResumeOnboarding } from "./components/ResumeOnboarding";
import { RedirectIfAuthed, RequireAuth } from "./lib/auth";
import { AgentePage } from "./pages/agente";
import { ConfiguracionPage } from "./pages/configuracion";
import { ConsultasPage } from "./pages/consultas";
import { IngresoPage } from "./pages/ingreso";
import { InicioPage } from "./pages/inicio";
import { OnboardingPage } from "./pages/onboarding";
import { PropiedadesPage } from "./pages/propiedades";

export const router = createBrowserRouter([
  {
    path: "/ingreso",
    element: (
      <RedirectIfAuthed>
        <IngresoPage />
      </RedirectIfAuthed>
    ),
  },
  {
    path: "/onboarding/:step?",
    element: (
      <RequireAuth>
        <OnboardingPage />
      </RequireAuth>
    ),
  },
  {
    element: (
      <RequireAuth>
        <RequireProfile>
          <ResumeOnboarding>
            <AppShell />
          </ResumeOnboarding>
        </RequireProfile>
      </RequireAuth>
    ),
    children: [
      { path: "/", element: <InicioPage /> },
      { path: "/consultas", element: <ConsultasPage /> },
      { path: "/propiedades", element: <PropiedadesPage /> },
      { path: "/agente", element: <AgentePage /> },
      { path: "/configuracion", element: <ConfiguracionPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
