import { Button, Card, CardContent, CardHeader, CardTitle, PanelSessionProvider } from "@followup/ui";
import type { SupabaseClient } from "@supabase/supabase-js";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { AccountApi } from "./account";
import { ACCOUNT_QUERY_KEY, ChangePasswordPage } from "./AccountPages";
import { ApiRequestError } from "./api";
import { useAuth as useShellAuth } from "./auth/AuthProvider";
import type { AuthMode } from "./auth/mode";
import type { MeLike } from "./RequireProfile";
import { SignIn } from "./SignIn";

function accessError(error: unknown, productName: string): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return "Tu sesión no es válida o venció. Cerrá sesión y volvé a entrar.";
    }
    if (error.code === "profile_not_found") {
      return `Este usuario no tiene una cuenta en ${productName}. Pedile acceso a un administrador.`;
    }
    return "No pudimos verificar tu acceso. Probá de nuevo.";
  }
  return "No pudimos conectarnos con el servidor. Revisá tu conexión y probá de nuevo.";
}

function AccessCard({
  email,
  title,
  message,
  onRetry,
  onSignOut,
}: {
  email: string;
  title: string;
  message: string;
  onRetry?: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="auth-backdrop flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground" role={onRetry ? "alert" : undefined}>
            {message}
          </p>
          {email ? (
            <p className="text-sm">
              Entraste como <span className="font-medium">{email}</span>
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {onRetry ? <Button onClick={onRetry}>Reintentar</Button> : null}
            <Button variant="outline" onClick={onSignOut}>
              Cerrar sesión
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export interface RequireAdminProps {
  /** "inmo24x7", "Cuentas Claras": whose backoffice this is. */
  productName: string;
  fetchMe: () => Promise<MeLike>;
  account: AccountApi;
  authMode: AuthMode;
  getSupabase: () => SupabaseClient;
  useAuth?: typeof useShellAuth;
  children: ReactNode;
}

/** The backoffice's gate: platform admins of this product only. */
export function RequireAdmin({
  productName,
  fetchMe,
  account,
  authMode,
  getSupabase,
  useAuth = useShellAuth,
  children,
}: RequireAdminProps) {
  const { session, loading, signOut } = useAuth();
  const accountQuery = useQuery({
    queryKey: ACCOUNT_QUERY_KEY,
    queryFn: account.fetchAccount,
    enabled: !loading && Boolean(session),
    retry: false,
  });
  const mustChange = accountQuery.data?.must_change_password === true;
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !loading && Boolean(session) && accountQuery.isFetched && !mustChange,
    retry: false,
  });

  if (loading) {
    return null;
  }
  if (!session) {
    return (
      <SignIn
        productName={productName}
        areaName="Backoffice"
        title="Entrá al backoffice"
        description="Solo administradores de la plataforma."
        authMode={authMode}
        getSupabase={getSupabase}
        account={account}
        devPlaceholder="admin@local.test"
      />
    );
  }
  if (mustChange) {
    return (
      <ChangePasswordPage
        productName={productName}
        areaName="Backoffice"
        account={account}
        authMode={authMode}
        getSupabase={getSupabase}
        useAuth={useAuth}
      />
    );
  }
  if (accountQuery.isPending || meQuery.isPending) {
    return <p className="p-8 text-sm text-muted-foreground">Cargando...</p>;
  }
  if (meQuery.isError) {
    return (
      <AccessCard
        email={session.email}
        title="No pudimos entrar al backoffice"
        message={accessError(meQuery.error, productName)}
        onRetry={() => void meQuery.refetch()}
        onSignOut={() => void signOut()}
      />
    );
  }
  if (!meQuery.data.profile.is_platform_admin) {
    return (
      <AccessCard
        email={session.email || meQuery.data.profile.email}
        title="Backoffice"
        message="Solo administradores de la plataforma."
        onSignOut={() => void signOut()}
      />
    );
  }
  return (
    <PanelSessionProvider
      value={{
        email: session.email || meQuery.data.profile.email,
        onSignOut: () => void signOut(),
      }}
    >
      {children}
    </PanelSessionProvider>
  );
}
