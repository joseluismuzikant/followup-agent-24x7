import { RequireProfile as ShellRequireProfile } from "@followup/app-shell";
import type { ReactNode } from "react";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";

export function RequireProfile({ children }: { children: ReactNode }) {
  return (
    <ShellRequireProfile fetchMe={fetchMe} useAuth={useAuth}>
      {children}
    </ShellRequireProfile>
  );
}
