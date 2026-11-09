import { useCallback, useSyncExternalStore } from "react";

/** Tailwind's `md` and `lg` breakpoints, for layouts that render a different tree per size
 * (one table or one card list, not both hidden with CSS). */
export const MD_UP = "(min-width: 48rem)";
export const LG_UP = "(min-width: 64rem)";

/** Whether `query` matches, updated on resize. Without `matchMedia` (jsdom, old browsers) it
 * is `fallback`: the desktop layout by default. */
export function useMediaQuery(query: string, fallback = true): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return () => undefined;
      }
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  const snapshot = () =>
    typeof window === "undefined" || typeof window.matchMedia !== "function"
      ? fallback
      : window.matchMedia(query).matches;
  return useSyncExternalStore(subscribe, snapshot, () => fallback);
}
