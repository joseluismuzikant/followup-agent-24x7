import { describe, expect, it } from "vitest";

import { scrubDeep, scrubText, withoutQuery } from "./scrub";

describe("scrubText (same cases as the API's scrubber)", () => {
  it.each([
    ["Escribime a ana.perez+casa@gmail.com", "Escribime a <email>"],
    ["Mi cel es +54 9 11 5555-1234", "Mi cel es <phone>"],
    ["llamame al 011 15 4444-5555", "llamame al <phone>"],
    ["(0351) 456-7890", "<phone>"],
    ["1123456789", "<phone>"],
    ["DNI 30.123.456", "DNI <dni>"],
    ["dni 30123456", "dni <phone>"],
    ["Authorization: Bearer abc.def-123_xyz", "Authorization: Bearer <token>"],
    ["token eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl here", "token <jwt> here"],
    ["id 9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11", "id 9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11"],
  ])("%s", (text, expected) => {
    expect(scrubText(text)).toBe(expected);
  });

  it("scrubs nested values and keeps the rest", () => {
    expect(scrubDeep({ a: ["ana@x.com", 3], b: { c: null, d: "ok" } })).toEqual({
      a: ["<email>", 3],
      b: { c: null, d: "ok" },
    });
  });

  it("drops query strings and fragments", () => {
    expect(withoutQuery("https://app.x.com/consultas?q=ana#top")).toBe("https://app.x.com/consultas");
    expect(withoutQuery("/inicio")).toBe("/inicio");
  });
});
