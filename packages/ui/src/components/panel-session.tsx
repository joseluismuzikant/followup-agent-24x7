import { createContext, useContext } from "react";

export interface PanelSession {
  email: string;
  onSignOut: () => void;
}

const PanelSessionContext = createContext<PanelSession | null>(null);

/** Who is signed in, for PanelLayout's sidebar ("Cerrar sesión"). The panels' AppShell and the
 * backoffices' admin gate provide it; without it the sidebar shows no session block. */
export const PanelSessionProvider = PanelSessionContext.Provider;

export function usePanelSession(): PanelSession | null {
  return useContext(PanelSessionContext);
}
