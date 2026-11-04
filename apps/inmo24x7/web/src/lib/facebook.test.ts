import { describe, expect, it } from "vitest";

import { isFacebookOrigin, parseSignupMessage } from "./facebook";

const finish = JSON.stringify({
  type: "WA_EMBEDDED_SIGNUP",
  event: "FINISH",
  data: { waba_id: "w1", phone_number_id: "p1" },
});

describe("isFacebookOrigin", () => {
  it.each(["https://www.facebook.com", "https://facebook.com", "https://web.facebook.com"])(
    "accepts %s",
    (origin) => {
      expect(isFacebookOrigin(origin)).toBe(true);
    },
  );

  it.each([
    "https://evilfacebook.com",
    "https://facebook.com.evil.com",
    "http://www.facebook.com",
    "https://www.facebook.com.evil.com",
    "https://notfacebook.com",
    "null",
    "",
    "facebook.com",
  ])("rejects %s", (origin) => {
    expect(isFacebookOrigin(origin)).toBe(false);
  });
});

describe("parseSignupMessage", () => {
  it("reads Meta's message only from facebook.com", () => {
    expect(parseSignupMessage("https://www.facebook.com", finish)?.event).toBe("FINISH");
    expect(parseSignupMessage("https://evilfacebook.com", finish)).toBeNull();
    expect(parseSignupMessage("https://facebook.com.evil.com", finish)).toBeNull();
  });
});
