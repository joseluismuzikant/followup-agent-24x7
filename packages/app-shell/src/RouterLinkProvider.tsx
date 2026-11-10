import { LinkProvider } from "@followup/ui";
import type * as React from "react";
import { Link } from "react-router";

function RouterLink({ href, ...props }: React.ComponentProps<"a"> & { href: string }) {
  return <Link to={href} {...props} />;
}

/** @followup/ui's internal links (the panel's menu, checklist items) as router links: a
 * click changes the page in place instead of reloading the whole app. Wrap the app's
 * RouterProvider with it; the links themselves render inside the router. */
export function RouterLinkProvider({ children }: { children: React.ReactNode }) {
  return <LinkProvider component={RouterLink}>{children}</LinkProvider>;
}
