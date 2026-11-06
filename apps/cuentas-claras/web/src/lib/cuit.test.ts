import { describe, expect, it } from "vitest";

import { isValidCuit, looksLikePhone } from "./cuit";

describe("isValidCuit", () => {
  it("accepts a valid CUIT with or without dashes", () => {
    expect(isValidCuit("30-71234567-1")).toBe(true);
    expect(isValidCuit("20123456786")).toBe(true);
    expect(isValidCuit("30 50000000 3")).toBe(true);
  });

  it("rejects a wrong check digit, a wrong length and letters", () => {
    expect(isValidCuit("30-71234567-2")).toBe(false);
    expect(isValidCuit("3071234567")).toBe(false);
    expect(isValidCuit("30-7123456A-1")).toBe(false);
  });
});

describe("looksLikePhone", () => {
  it("wants an area code", () => {
    expect(looksLikePhone("11 5555-1234")).toBe(true);
    expect(looksLikePhone("+54 9 11 5555-1234")).toBe(true);
    expect(looksLikePhone("5555-1234")).toBe(false);
  });
});
