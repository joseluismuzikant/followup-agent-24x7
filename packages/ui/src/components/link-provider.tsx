import { createContext, useContext } from "react";
import type * as React from "react";

/** What @followup/ui renders for its internal links (the panel's menu, checklist items). */
export type LinkComponent = React.ComponentType<React.ComponentProps<"a"> & { href: string }>;

function PlainLink(props: React.ComponentProps<"a"> & { href: string }) {
  return <a {...props} />;
}

const LinkContext = createContext<LinkComponent>(PlainLink);

/** Lets an app render the library's internal links with its router (a client-side
 * navigation instead of reloading the whole app). Without it they are plain anchors. */
export function LinkProvider({
  component,
  children,
}: {
  component: LinkComponent;
  children: React.ReactNode;
}) {
  return <LinkContext.Provider value={component}>{children}</LinkContext.Provider>;
}

export function useLinkComponent(): LinkComponent {
  return useContext(LinkContext);
}
