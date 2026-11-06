import { describe, expect, it } from "vitest";

import { countLabel, formatAmount, shortDate, todayIso } from "./format";

describe("format", () => {
  it("shows pesos and dollars the Argentine way", () => {
    expect(formatAmount("180000.50").replace(/\s/g, " ")).toBe("$ 180.000,5");
    expect(formatAmount("1200", "USD")).toBe("USD 1.200");
  });

  it("shows a date without shifting it by the timezone", () => {
    expect(shortDate("2026-10-01")).toBe("1 oct");
  });

  it("counts in Spanish", () => {
    expect(countLabel(1, "factura", "facturas")).toBe("1 factura");
    expect(countLabel(3, "factura", "facturas")).toBe("3 facturas");
  });

  it("gives today as YYYY-MM-DD", () => {
    expect(todayIso(new Date(2026, 10, 4, 23, 30))).toBe("2026-11-04");
  });
});
