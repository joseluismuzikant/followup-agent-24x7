import { createBrowserRouter, Navigate } from "react-router";

import { App } from "./App";
import { SimuladorPage } from "./pages/simulador";
import { WhatsAppPage } from "./pages/whatsapp";

export const router = createBrowserRouter([
  { path: "/", element: <App /> },
  { path: "/simulador", element: <SimuladorPage /> },
  { path: "/negocios/:tenantId/whatsapp", element: <WhatsAppPage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
