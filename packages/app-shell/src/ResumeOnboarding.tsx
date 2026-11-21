import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { isOnboardingDeferred } from "./onboarding-deferred";
import type { MeLike } from "./RequireProfile";

/** Owners and managers can edit the setup; other roles never see the wizard. */
export function canEditSetup(role: string): boolean {
  return role === "owner" || role === "manager";
}

export interface OnboardingLike {
  finished: boolean;
  completed_steps?: { step: string }[];
}

/**
 * Sends owners and managers back to the wizard after login.
 *
 * With `essentialSteps`, only while one of them is not completed (a brand-new account has
 * nothing to show yet); otherwise the page asked for opens, and Inicio's checklist leads back
 * to the wizard. Without it, while the wizard is unfinished.
 */
export function ResumeOnboarding({
  fetchMe,
  fetchOnboarding,
  essentialSteps,
  children,
}: {
  fetchMe: () => Promise<MeLike>;
  fetchOnboarding: () => Promise<OnboardingLike>;
  essentialSteps?: readonly string[];
  children: ReactNode;
}) {
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });

  if (onboardingQuery.isPending) {
    return null;
  }
  // If the onboarding record is unavailable, never block the panel on it.
  const onboarding = onboardingQuery.data;
  const unfinished = onboarding !== undefined && !onboarding.finished;
  const done = new Set((onboarding?.completed_steps ?? []).map((completed) => completed.step));
  const needsWizard =
    unfinished && (essentialSteps === undefined || essentialSteps.some((step) => !done.has(step)));
  const role = meQuery.data?.profile.role ?? "";
  if (needsWizard && canEditSetup(role) && !isOnboardingDeferred()) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}
