import { ResumeOnboarding as ShellResumeOnboarding } from "@followup/app-shell";
import type { ReactNode } from "react";

import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";

/** Sends owners and managers with an unfinished wizard back to it after login. */
export function ResumeOnboarding({ children }: { children: ReactNode }) {
  return (
    <ShellResumeOnboarding fetchMe={fetchMe} fetchOnboarding={fetchOnboarding}>
      {children}
    </ShellResumeOnboarding>
  );
}
