/**
 * Personal data never reaches Sentry: the same patterns the API uses for LangSmith and Sentry
 * (emails, Argentine phones, DNIs) plus tokens, and no query strings (links can carry them).
 */

const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
// "+54 9 11 1234-5678", "011 15 1234-5678", "(0351) 456-7890", "1123456789"; not inside longer
// tokens such as UUIDs.
const PHONE =
  /(?<![\w-])(?:\+?54[\s-]*)?(?:9[\s-]*)?(?:\(?0?\d{2,4}\)?[\s-]*)?(?:15[\s-]*)?\d{3,4}[\s-]?\d{4}(?![\w-])/g;
// "30.123.456", "30123456".
const DNI = /(?<![\w.-])(?:\d{1,2}\.\d{3}\.\d{3}|\d{7,8})(?![\w-]|\.\d)/g;
const BEARER = /\bbearer\s+[\w.~+/=-]+/gi;
const JWT = /\beyJ[\w-]+\.[\w-]+\.[\w-]+/g;

export function scrubText(value: string): string {
  return value
    .replace(BEARER, "Bearer <token>")
    .replace(JWT, "<jwt>")
    .replace(EMAIL, "<email>")
    .replace(PHONE, "<phone>")
    .replace(DNI, "<dni>");
}

/** Strings anywhere inside `value`, scrubbed; everything else as it was. */
export function scrubDeep<T>(value: T): T {
  if (typeof value === "string") {
    return scrubText(value) as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => scrubDeep(item)) as T;
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, scrubDeep(item)]),
    ) as T;
  }
  return value;
}

export function withoutQuery(url: string): string {
  const cut = url.search(/[?#]/);
  return cut === -1 ? url : url.slice(0, cut);
}
