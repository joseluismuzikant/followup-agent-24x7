import { createBrowserRouter, Navigate } from "react-router";

import { App } from "./App";
import { SimuladorPage } from "./pages/simulador";

export const router = createBrowserRouter([
  { path: "/", element: <App /> },
  { path: "/simulador", element: <SimuladorPage /> },
  { path: "*", element: <Navigate to="/" replace /> },
]);
