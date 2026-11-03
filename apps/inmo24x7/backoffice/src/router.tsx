import { createBrowserRouter, Navigate } from "react-router";

import { App } from "./App";
import { NegocioPage } from "./pages/negocio";
import { PlanesPage } from "./pages/planes";
import { SimuladorPage } from "./pages/simulador";
import { SistemaPage } from "./pages/sistema";
import { WhatsAppPage } from "./pages/whatsapp";

export const router = createBrowserRouter([
  { path: "/", element: <App /> },
  { path: "/negocios/:tenantId", element: <NegocioPage /> },
  { path: "/negocios/:tenantId/whatsapp", element: <WhatsAppPage /> },
  { path: "/simulador", element: <SimuladorPage /> },
  { path: "/sistema", element: <SistemaPage /> },
  { path: "/planes", element: <PlanesPage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
