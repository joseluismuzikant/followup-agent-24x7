import { PanelLayout, PanelSessionProvider } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";
import { PRODUCT_NAME } from "../lib/product";

const navItems = [
  { label: "Inicio", href: "/" },
  { label: "Facturas", href: "/facturas" },
  { label: "Clientes", href: "/clientes" },
  { label: "Recordatorios y cobros", href: "/recordatorios" },
  { label: "Configuración", href: "/configuracion" },
];

export function AppShell() {
  const location = useLocation();
  const { session, signOut } = useAuth();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });

  const items = navItems.map((item) => ({
    ...item,
    active:
      item.href === "/" ? location.pathname === "/" : location.pathname.startsWith(item.href),
  }));

  return (
    <PanelSessionProvider
      value={{
        email: session?.email || meQuery.data?.profile.email || "",
        onSignOut: () => void signOut(),
      }}
    >
      <PanelLayout
        productName={PRODUCT_NAME}
        areaName="Panel"
        title={items.find((item) => item.active)?.label ?? "Inicio"}
        description="Tus facturas y tus clientes, al día."
        navItems={items}
        subtitle={meQuery.data?.tenant.name}
      >
        <Outlet />
      </PanelLayout>
    </PanelSessionProvider>
  );
}
