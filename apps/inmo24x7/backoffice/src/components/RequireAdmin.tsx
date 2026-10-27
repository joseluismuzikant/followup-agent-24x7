import { Button, Card, CardContent, CardHeader, CardTitle } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";
import { supabase } from "../lib/supabase";

function BackofficeSignIn() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signInWithGoogle() {
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithOAuth({
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
    const { error: signInError } = await supabase.auth.signInWithOtp({
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
        </CardContent>
      </Card>
    </div>
  );
}

export function RequireAdmin({ children }: { children: ReactNode }) {
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
    return <BackofficeSignIn />;
  }
  if (meQuery.isPending) {
    return <p className="p-8 text-sm text-muted-foreground">Cargando...</p>;
  }
  if (meQuery.isError || !meQuery.data.profile.is_platform_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-muted-foreground">
          Solo administradores de la plataforma.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
