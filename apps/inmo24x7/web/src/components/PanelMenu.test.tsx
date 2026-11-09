import { PanelLayout } from "@followup/ui";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { phoneViewport } from "../test-fixtures";

const navItems = [
  { label: "Inicio", href: "#inicio", active: true },
  { label: "Consultas", href: "#consultas" },
];

function renderLayout() {
  render(
    <PanelLayout
      productName="inmo24x7"
      areaName="Panel"
      title="Inicio"
      navItems={navItems}
      subtitle="Inmobiliaria Sur"
      action={<button type="button">Cerrar sesión</button>}
    >
      <p>Contenido</p>
    </PanelLayout>,
  );
  return userEvent.setup();
}

describe("PanelLayout's phone menu", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is a sidebar on desktop, with no menu button", () => {
    renderLayout();

    expect(screen.getByRole("navigation", { name: "Navegación principal" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Abrir el menú" })).toBeNull();
  });

  it("opens a drawer that keeps focus, closes on Escape and returns focus", async () => {
    phoneViewport(390);
    const user = renderLayout();
    const opener = screen.getByRole("button", { name: "Abrir el menú" });
    // The header's own controls stay reachable without opening the menu.
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeTruthy();

    await user.click(opener);

    const drawer = screen.getByRole("dialog", { name: "Menú (estás en Inicio)" });
    expect(opener.getAttribute("aria-expanded")).toBe("true");
    expect(drawer.contains(document.activeElement)).toBe(true);
    const links = within(drawer).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Inicio", "Consultas"]);

    // Tab from the last control wraps to the first one inside the drawer.
    links.at(-1)?.focus();
    await user.tab();
    expect(drawer.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Abrir el menú" }));
  });

  it("closes when a page is picked", async () => {
    phoneViewport(360);
    const user = renderLayout();
    await user.click(screen.getByRole("button", { name: "Abrir el menú" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Consultas" }));

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
