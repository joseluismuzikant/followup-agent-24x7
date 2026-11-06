/** The CUIT's check (the API checks the same): 11 digits, the last one is the mod-11
 * check digit with AFIP's weights (remainder 1 has no valid digit). Dashes and spaces are allowed. */
const WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];

export function isValidCuit(value: string): boolean {
  const digits = value.replace(/[\s-]/g, "");
  if (!/^\d{11}$/.test(digits)) {
    return false;
  }
  const sum = WEIGHTS.reduce((total, weight, index) => total + weight * Number(digits[index]), 0);
  const remainder = sum % 11;
  if (remainder === 1) {
    return false;
  }
  return (remainder === 0 ? 0 : 11 - remainder) === Number(digits[10]);
}

/** An Argentine WhatsApp number, loosely: 10 to 13 digits once symbols are gone. The API
 * normalizes it (and rejects what it can't). */
export function looksLikePhone(value: string): boolean {
  const digits = value.replace(/[^\d]/g, "");
  return digits.length >= 10 && digits.length <= 13;
}
