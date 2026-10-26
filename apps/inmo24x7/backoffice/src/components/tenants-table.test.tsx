import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TenantsTable } from "./tenants-table";

describe("TenantsTable", () => {
  it("renders tenant names and slugs", () => {
    const html = renderToStaticMarkup(
      <TenantsTable
        tenants={[
          {
            id: "6d57c8d4-6b5b-4fac-8e50-23b6f0c0f210",
            name: "Inmobiliaria Sur",
            slug: "inmobiliaria-sur",
            created_at: "2026-10-26T15:17:45.102780Z",
          },
        ]}
      />,
    );

    expect(html).toContain("Inmobiliaria Sur");
    expect(html).toContain("inmobiliaria-sur");
  });
});
