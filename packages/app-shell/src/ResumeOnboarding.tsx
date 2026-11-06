import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { isOnboardingDeferred } from "./onboarding-deferred";
import type { MeLike } from "./RequireProfile";

/** Owners and managers can edit the setup; other roles never see the wizard. */
export function canEditSetup(role: string): boolean {
  return role === "owner" || role === "manager";
}

/** Sends owners and managers with an unfinished wizard back to it after login. */
export function ResumeOnboarding({
  fetchMe,
  fetchOnboarding,
  children,
}: {
  fetchMe: () => Promise<MeLike>;
  fetchOnboarding: () => Promise<{ finished: boolean }>;
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
  const unfinished = onboardingQuery.data && !onboardingQuery.data.finished;
  const role = meQuery.data?.profile.role ?? "";
  if (unfinished && canEditSetup(role) && !isOnboardingDeferred()) {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}
