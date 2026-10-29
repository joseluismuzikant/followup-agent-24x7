import { Button, PanelLayout } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";

const navItems = [
  { label: "Inicio", href: "/" },
  { label: "Consultas", href: "/consultas" },
  { label: "Propiedades", href: "/propiedades" },
  { label: "Agente", href: "/agente" },
  { label: "Configuración", href: "/configuracion" },
];

export function AppShell() {
  const location = useLocation();
  const { signOut } = useAuth();
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
  });

  const items = navItems.map((item) => ({
    ...item,
    active:
      item.href === "/" ? location.pathname === "/" : location.pathname.startsWith(item.href),
  }));

  const title =
    location.pathname === "/probar"
      ? "Probar el agente"
      : (items.find((item) => item.active)?.label ?? "Inicio");

  return (
    <PanelLayout
      productName="inmo24x7"
      areaName="Panel"
      title={title}
      description="Tu espacio de trabajo."
      navItems={items}
      subtitle={meQuery.data?.tenant.name}
      action={
        <Button variant="outline" onClick={() => void signOut()}>
          Cerrar sesión
        </Button>
      }
    >
      <Outlet />
    </PanelLayout>
  );
}
