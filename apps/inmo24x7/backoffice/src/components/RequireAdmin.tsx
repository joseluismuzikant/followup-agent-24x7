import { ApiRequestError } from "@followup/api-client-inmo24x7";
import { Button, Card, CardContent, CardHeader, CardTitle, DevSignIn } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";
import { authMode } from "../lib/auth-mode";
import { signInDev } from "../lib/dev-session";
import { getSupabase } from "../lib/supabase";

function BackofficeSignIn() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signInWithGoogle() {
    setError(null);
    const { error: signInError } = await getSupabase().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (signInError) {
      setError("No pudimos iniciar sesión.");
    }
  }

  async function sendMagicLink(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) {
      setError("Ingresá tu email.");
      return;
    }
    setError(null);
    const { error: signInError } = await getSupabase().auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    if (signInError) {
      setError("No pudimos enviar el link.");
    } else {
      setSent(true);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Backoffice</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {authMode === "supabase" ? (
            <>
              <Button type="button" onClick={() => void signInWithGoogle()}>
                Continuar con Google
              </Button>
              {sent ? (
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  Te enviamos un link a {email}.
                </p>
              ) : (
                <form onSubmit={(event) => void sendMagicLink(event)} className="flex flex-col gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="tu@email.com"
                    className="h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                  <Button type="submit" variant="outline">
                    Enviarme un link para entrar
                  </Button>
                </form>
              )}
              {error ? (
                <p className="text-sm text-destructive" aria-live="polite">
                  {error}
                </p>
              ) : null}
            </>
          ) : (
            <DevSignIn onSignIn={signInDev} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function accessError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return "Tu sesión no es válida o venció. Cerrá sesión y volvé a entrar.";
    }
    if (error.code === "profile_not_found") {
      return "Este usuario no tiene una cuenta en inmo24x7. Pedile acceso a un administrador.";
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
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
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

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { session, loading, signOut } = useAuth();
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !loading && Boolean(session),
    retry: false,
  });

  if (loading) {
    return null;
  }
  if (!session) {
    return <BackofficeSignIn />;
  }
  if (meQuery.isPending) {
    return <p className="p-8 text-sm text-muted-foreground">Cargando...</p>;
  }
  if (meQuery.isError) {
    return (
      <AccessCard
        email={session.email}
        title="No pudimos entrar al backoffice"
        message={accessError(meQuery.error)}
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
  return <>{children}</>;
}
