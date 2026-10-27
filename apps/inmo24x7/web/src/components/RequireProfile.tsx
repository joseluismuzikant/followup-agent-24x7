import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";

export function RequireProfile({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !loading && Boolean(session),
  });

  if (loading) {
    return null;
  }
  if (!session) {
    return <Navigate to="/ingreso" replace />;
  }
  if (meQuery.isPending) {
    return null;
  }
  if (meQuery.isError) {
    if (
      meQuery.error instanceof ApiRequestError &&
      meQuery.error.code === "profile_not_found"
    ) {
      return <Navigate to="/onboarding" replace />;
    }
    return <Navigate to="/ingreso" replace />;
  }
  return <>{children}</>;
}
