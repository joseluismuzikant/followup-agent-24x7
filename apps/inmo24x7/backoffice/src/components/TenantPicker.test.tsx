import type { Tenant } from "@followup/api-client-inmo24x7";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { filterTenants, TenantPicker } from "./TenantPicker";

const tenant = (id: string, name: string, slug: string): Tenant => ({
  id,
  name,
  slug,
  created_at: "2026-10-26T15:17:45Z",
  status: "active",
  trial_ends_at: "2026-11-09T15:17:45Z",
});

const tenants = [
  tenant("1", "Inmobiliaria Sur", "inmobiliaria-sur"),
  tenant("2", "Núñez Propiedades", "nunez-propiedades"),
  tenant("3", "Belgrano Homes", "belgrano-homes"),
];

function picker(query: string, selectedId: string | null = null) {
  return renderToStaticMarkup(
    <TenantPicker
      tenants={tenants}
      query={query}
      onQueryChange={() => {}}
      selectedId={selectedId}
      onSelect={() => {}}
    />,
  );
}

describe("TenantPicker", () => {
  it("searches by name ignoring case and accents, or by slug", () => {
    expect(filterTenants(tenants, "nunez").map((t) => t.id)).toEqual(["2"]);
    expect(filterTenants(tenants, "SUR").map((t) => t.id)).toEqual(["1"]);
    expect(filterTenants(tenants, "belgrano-h").map((t) => t.id)).toEqual(["3"]);
    expect(filterTenants(tenants, "  ")).toHaveLength(3);
  });

  it("lists only matching businesses and marks the selected one", () => {
    const html = picker("propiedades", "2");

    expect(html).toContain("Núñez Propiedades");
    expect(html).not.toContain("Inmobiliaria Sur");
    expect(html).toContain('aria-pressed="true"');
  });

  it("says when nothing matches", () => {
    expect(picker("zzz")).toContain("No encontramos negocios con ese nombre.");
  });
});
