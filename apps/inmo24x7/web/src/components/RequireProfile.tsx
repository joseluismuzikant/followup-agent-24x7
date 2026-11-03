import { ApiRequestError } from "@followup/api-client-inmo24x7";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { Navigate, useNavigate } from "react-router";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";

export function RequireProfile({ children }: { children: ReactNode }) {
  const { session, loading, signOut } = useAuth();
  const navigate = useNavigate();
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !loading && Boolean(session),
  });

  const unauthorized =
    meQuery.error instanceof ApiRequestError && meQuery.error.status === 401;

  useEffect(() => {
    if (unauthorized) {
      void signOut().then(() => navigate("/ingreso", { replace: true }));
    }
  }, [unauthorized, signOut, navigate]);

  if (loading) {
    return null;
  }
  if (!session) {
    return <Navigate to="/ingreso" replace />;
  }
  if (meQuery.isPending || unauthorized) {
    return null;
  }
  const suspended =
    (meQuery.data?.tenant.status === "suspended" && !meQuery.data.profile.is_platform_admin) ||
    (meQuery.error instanceof ApiRequestError && meQuery.error.code === "tenant_suspended");
  if (suspended) {
    return (
      <SuspendedAccount
        supportEmail={meQuery.data?.support_email ?? ""}
        onSignOut={() => void signOut()}
      />
    );
  }
  if (meQuery.isError) {
    if (
      meQuery.error instanceof ApiRequestError &&
      meQuery.error.code === "profile_not_found"
    ) {
      return <Navigate to="/onboarding" replace />;
    }
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>No pudimos cargar tu cuenta</CardTitle>
            <CardDescription>
              Hubo un problema al conectarnos con el servicio. Probá de nuevo en unos
              segundos.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button onClick={() => void meQuery.refetch()} disabled={meQuery.isFetching}>
              Reintentar
            </Button>
            <Button variant="outline" onClick={() => void signOut()}>
              Cerrar sesión
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  return <>{children}</>;
}

function SuspendedAccount({
  supportEmail,
  onSignOut,
}: {
  supportEmail: string;
  onSignOut: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Tu cuenta está suspendida</CardTitle>
          <CardDescription>
            Tu cuenta está suspendida. Escribinos a{" "}
            {supportEmail ? (
              <a className="font-medium text-primary" href={`mailto:${supportEmail}`}>
                {supportEmail}
              </a>
            ) : (
              "soporte"
            )}
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={onSignOut}>
            Cerrar sesión
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
