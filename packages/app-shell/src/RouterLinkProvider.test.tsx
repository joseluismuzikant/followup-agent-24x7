import { PanelLayout } from "@followup/ui";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { RouterLinkProvider } from "./RouterLinkProvider";

function Page() {
  const location = useLocation();
  return <p>Estás en {location.pathname}</p>;
}

describe("RouterLinkProvider", () => {
  it("turns the panel's menu into router links (no reload)", async () => {
    const user = userEvent.setup();
    render(
      <RouterLinkProvider>
        <MemoryRouter initialEntries={["/"]}>
          <PanelLayout
            productName="inmo24x7"
            areaName="Panel"
            title="Inicio"
            navItems={[
              { label: "Inicio", href: "/", active: true },
              { label: "Consultas", href: "/consultas" },
            ]}
          >
            <Routes>
              <Route path="*" element={<Page />} />
            </Routes>
          </PanelLayout>
        </MemoryRouter>
      </RouterLinkProvider>,
    );

    await user.click(screen.getByRole("link", { name: "Consultas" }));

    // A plain anchor would leave MemoryRouter at "/" (jsdom does not navigate).
    expect(screen.getByText("Estás en /consultas")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Consultas" }).getAttribute("href")).toBe("/consultas");
  });
});
