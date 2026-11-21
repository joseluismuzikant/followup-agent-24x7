import { ResumeOnboarding as ShellResumeOnboarding } from "@followup/app-shell";
import type { ReactNode } from "react";

import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";

/** Without the business there is nothing to show: the wizard. After that, Inicio's checklist. */
const ESSENTIAL_STEPS = ["business"] as const;

/** Sends owners and managers to the wizard after login only while the business is missing. */
export function ResumeOnboarding({ children }: { children: ReactNode }) {
  return (
    <ShellResumeOnboarding
      fetchMe={fetchMe}
      fetchOnboarding={fetchOnboarding}
      essentialSteps={ESSENTIAL_STEPS}
    >
      {children}
    </ShellResumeOnboarding>
  );
}
