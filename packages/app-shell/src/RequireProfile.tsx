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

import { ApiRequestError } from "./api";
import { useAuth as useShellAuth } from "./auth/AuthProvider";

/** The part of /me every panel reads. */
export interface MeLike {
  profile: { id: string; role: string; email: string; is_platform_admin: boolean };
  tenant: { id: string; status: string };
  support_email: string;
}

/** The panel's gate: signed in, with a profile (a business) in this product, not
 * suspended. Without a profile it sends the person to /onboarding to create one. */
export function RequireProfile({
  fetchMe,
  useAuth = useShellAuth,
  children,
}: {
  fetchMe: () => Promise<MeLike>;
  /** The session hook; the app's own module, so tests can mock it. */
  useAuth?: typeof useShellAuth;
  children: ReactNode;
}) {
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
    if (
      meQuery.error instanceof ApiRequestError &&
      meQuery.error.code === "password_change_required"
    ) {
      return <Navigate to="/cambiar-clave" replace />;
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
    <div className="auth-backdrop flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xl">Tu cuenta está suspendida</CardTitle>
          <CardDescription>
            Tu cuenta está suspendida. Escribinos a{" "}
            {supportEmail ? (
              <a className="font-medium text-brand underline" href={`mailto:${supportEmail}`}>
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
