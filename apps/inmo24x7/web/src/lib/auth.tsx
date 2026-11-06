import { AuthProvider as ShellAuthProvider } from "@followup/app-shell";
import type { ReactNode } from "react";

import { authAdapter } from "./auth-adapter";

export { RedirectIfAuthed, RequireAuth, useAuth } from "@followup/app-shell";

export function AuthProvider({ children }: { children: ReactNode }) {
  return <ShellAuthProvider adapter={authAdapter}>{children}</ShellAuthProvider>;
}
