import type { PanelNavItem } from "@followup/ui";

const items = [
  { label: "Negocios", href: "/" },
  { label: "Simulador", href: "/simulador" },
];

export function navItems(pathname: string): PanelNavItem[] {
  return items.map((item) => ({
    ...item,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));
}

/** Sample property links point to the panel, which serves the placeholder page. */
const panelUrl = (import.meta.env.VITE_PANEL_URL ?? "http://localhost:5173").replace(/\/$/, "");

export function panelLink(path: string): string {
  return path.startsWith("/") ? `${panelUrl}${path}` : path;
}
