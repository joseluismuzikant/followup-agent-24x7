import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";
import { isOnboardingDeferred } from "../lib/onboarding-deferred";
import { canEditSetup } from "../lib/setup";

/** Sends owners and managers with an unfinished wizard back to it after login. */
export function ResumeOnboarding({ children }: { children: ReactNode }) {
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
  const unfinished = onboardingQuery.data && !onboardingQuery.data.finished;
  const role = meQuery.data?.profile.role ?? "";
  if (unfinished && canEditSetup(role) && !isOnboardingDeferred()) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}
