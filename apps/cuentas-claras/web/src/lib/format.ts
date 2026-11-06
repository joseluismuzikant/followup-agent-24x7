/** Amounts come as decimal strings ("180000.50"): shown the Argentine way. */
const ars = new Intl.NumberFormat("es-AR", {
  style: "currency",
  currency: "ARS",
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});
const plain = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });

export function formatAmount(amount: string, currency: string = "ARS"): string {
  const value = Number(amount);
  return currency === "USD" ? `USD ${plain.format(value)}` : ars.format(value);
}

/** "10 oct" (dates come as YYYY-MM-DD, local days, no timezone shift). */
export function shortDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year!, month! - 1, day!)
    .toLocaleDateString("es-AR", { day: "numeric", month: "short" })
    .replace(".", "");
}

export function longDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year!, month! - 1, day!).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function countLabel(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** Today on this device, as YYYY-MM-DD (a payment date's default). */
export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
